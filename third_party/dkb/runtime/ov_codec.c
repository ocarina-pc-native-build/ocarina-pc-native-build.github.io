// nn::codec video decoding (the Switch 2 SDK's VP9 path) on the host with libvpx, for Donkey Kong Bananza's tutorial
// guide movies (Movie/Guide*.webm, 960x540). The SDK's nn::codec::video::Initialize opens the console's video service
// over IPC, which the host does not serve (the first guide movie crashed in nn::codec::video::detail::ipc::Initialize),
// so the decoder calls are host functions. The demuxer (nn::movie::MediaExtractor) stays guest code.
// What the game's movie player (main+0xdfb8xx..0xdfe9xx) expects, read from its code:
// - each output buffer i is an image pool of its own, tied to i by RegisterVp9DecoderBuffer; the player reads the
//   pool's size at +0x20 / +0x22 (u16 width, height), which InitializeDecoderImagePool takes from the preference
//   (MakeDecodeImagePreference, SDK code: +8 u16 width - 1, +10 u16 height - 1);
// - it acquires an output buffer before it submits input (its wrapper aborts on any failure there): Acquire reserves
//   the buffer the next shown picture goes to and returns a fence (NativeSyncHandle, which the caller zeroed; the
//   host writes a token in its first word); the player waits for it through nn::syncpt::sdk::RequestSyncPointEvent,
//   signalled when SubmitVp9DecoderInputBuffer has decoded a picture into that buffer (at once if it already has);
// - a submission with no reserved buffer to decode into answers "not ready" (the wrapper's retry code 0x76);
// - the picture is read with ReadDecoderOutputImageNv12 (Y plane, then interleaved UV, each with the caller's pitch).
//   GetDecoderImagePoolNativeImageHandle (the player's GPU path) has no image yet and returns 0.
// libvpx is BSD-3-Clause and already linked for ov_movie.c.
// AV1 extension: dav1d (BSD-2-Clause), the supplied newer SDK's exported
// transfer/remote-memory signatures, direct ready-event pointer, and no-color-space
// output-properties ABI. Both codecs share the existing buffer/fence queue.
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <dav1d/dav1d.h>

#include <vpx/vp8dx.h>
#include <vpx/vpx_decoder.h>

#include "host.h"
#include "platform/platform.h"

enum { R_NOT_READY = 0x1c266f };   // (result & 0x3fffff) - 0x1c2000 == 0x66f: "try again" for the game's wrapper
// QUEUED: packets the decoder takes ahead of the buffers for their pictures, as Eglantine's video session does
// (nx2_gsv.h, INx2VideoSession::MaxQueuedInputs); a submission past them answers "not ready".
enum { SLOTS = 16, DECODERS = 4, WAITERS = 4, QUEUED = 8 };
enum { S_FREE, S_WAIT, S_FILLED };   // registered; acquired with no picture yet; acquired holding a picture
enum { FENCE_TAG = 0xc0de0000u };    // fence token: tag | decoder << 8 | buffer

// TOTK_TRACE=codec: a line for each decoder call that moves a buffer or a picture, to follow a player that stops.
#define TRACE(...)                                                                                                   \
    do {                                                                                                             \
        if (rt_trace & RT_TRACE_CODEC) rt_log("codec: " __VA_ARGS__);                                                \
    } while (0)

#define LOG_FIRST(...)                                                                                               \
    do {                                                                                                             \
        static volatile int32_t logged;                                                                              \
        if (!__atomic_exchange_n(&logged, 1, __ATOMIC_RELAXED)) rt_log(__VA_ARGS__);                                 \
    } while (0)

typedef struct {
    uint64_t pool;     // guest VideoDecoderImagePoolType registered for this index; 0: not registered
    int state;
    uint32_t seq;      // acquisition order: pictures fill the oldest waiting buffer
    uint64_t waiter[WAITERS];   // guest system events of sync point events requested before the picture came
    uint16_t w, h;
    int64_t pts;       // nanoseconds (nn::TimeSpan)
    int eos;
    uint8_t *nv12;     // w*h luma, then cw*ch interleaved UV pairs
} Slot;

// A packet submitted while no buffer was reserved for its picture, decoded once one is (ov_vp9_acquire).
typedef struct { uint8_t *data; size_t size; int64_t pts; int end; } Packet;

typedef struct {
    uint64_t key;      // guest Vp9DecoderType; 0: unused
    vpx_codec_ctx_t vpx;
    int vpx_ok;
    Dav1dContext *av1; // AV1 movies use the same guest image-pool/fence lifecycle as VP9.
    uint32_t seq;
    Slot slot[SLOTS];
    Slot last;         // the newest picture, for packets that show none
    Packet queue[QUEUED];
    int qhead, qn;
} Dec;

static Dec decs[DECODERS];
static PlatMutex lock = PLAT_MUTEX_INIT;   // every decoder call; held across a decode (one 960x540 frame, a few ms)

static Dec *dec_of(uint64_t key) {
    for (int i = 0; i < DECODERS; i++)
        if (decs[i].key == key) return &decs[i];
    return NULL;
}

static uint32_t cw(uint16_t w) { return (w + 1u) / 2; }
static uint32_t ch(uint16_t h) { return (h + 1u) / 2; }

// Copies a decoded I420 picture into s as NV12.
static void put_picture(Slot *s, const vpx_image_t *img) {
    uint16_t w = (uint16_t)img->d_w, h = (uint16_t)img->d_h;
    if (!s->nv12 || s->w != w || s->h != h) {
        free(s->nv12);
        s->nv12 = malloc((size_t)w * h + 2 * (size_t)cw(w) * ch(h));
        if (!s->nv12) rt_fatal("codec: out of memory for a %ux%u picture", w, h);
        s->w = w, s->h = h;
    }
    for (uint32_t y = 0; y < h; y++) memcpy(s->nv12 + (size_t)y * w, img->planes[0] + (size_t)y * img->stride[0], w);
    uint8_t *uv = s->nv12 + (size_t)w * h;
    for (uint32_t y = 0; y < ch(h); y++) {
        const uint8_t *u = img->planes[1] + (size_t)y * img->stride[1], *v = img->planes[2] + (size_t)y * img->stride[2];
        uint8_t *o = uv + (size_t)y * 2 * cw(w);
        for (uint32_t x = 0; x < cw(w); x++) o[2 * x] = u[x], o[2 * x + 1] = v[x];
    }
}

static void copy_slot(Slot *to, const Slot *from) {
    if (!from->nv12) return;
    size_t n = (size_t)from->w * from->h + 2 * (size_t)cw(from->w) * ch(from->h);
    if (!to->nv12 || to->w != from->w || to->h != from->h) {
        free(to->nv12);
        if (!(to->nv12 = malloc(n))) rt_fatal("codec: out of memory for a picture");
        to->w = from->w, to->h = from->h;
    }
    memcpy(to->nv12, from->nv12, n);
}

static void queue_drop(Dec *d) {
    for (int i = 0; i < d->qn; i++) free(d->queue[(d->qhead + i) % QUEUED].data);
    d->qhead = d->qn = 0;
}

// The oldest reserved buffer still waiting for a picture: pictures fill buffers in acquisition order.
static Slot *oldest_wait(Dec *d) {
    Slot *s = NULL;
    for (int i = 0; i < SLOTS; i++)
        if (d->slot[i].state == S_WAIT && (!s || (int32_t)(d->slot[i].seq - s->seq) < 0)) s = &d->slot[i];
    return s;
}

// Decodes one packet into the waiting buffer s (lock held). A packet that shows nothing leaves s waiting, except the
// last one: the player then gets the previous picture (or black) marked as the end. Returns the number of events to
// signal, stored in wake.
static int decode_into(Dec *d, Slot *s, const uint8_t *data, size_t size, int64_t pts, int end, uint64_t wake[WAITERS]) {
    const vpx_image_t *img = NULL, *f;
    Dav1dPicture av1_picture = {0};
    vpx_image_t av1_view = {0};
    if (d->av1) {
        Dav1dData packet = {0};
        if (size) {
            uint8_t *copy = dav1d_data_create(&packet, size);
            if (!copy) rt_fatal("codec: AV1 packet allocation failed");
            memcpy(copy, data, size);
            packet.m.timestamp = pts;
        }
        // Follow dav1d_send_data/get_picture ownership and EAGAIN rules. A movie
        // sample normally contains one shown frame; never silently discard extras.
        for (;;) {
            int sent = packet.sz ? dav1d_send_data(d->av1, &packet) : 0;
            if (sent < 0 && sent != DAV1D_ERR(EAGAIN)) {
                dav1d_data_unref(&packet);
                rt_fatal("codec: AV1 input rejected (%d)", sent);
            }
            Dav1dPicture picture = {0};
            int got = dav1d_get_picture(d->av1, &picture);
            if (got == 0) {
                if (av1_picture.data[0]) rt_fatal("codec: AV1 sample contains multiple shown frames; output queue required");
                av1_picture = picture;
            } else if (got != DAV1D_ERR(EAGAIN)) {
                dav1d_data_unref(&packet);
                rt_fatal("codec: AV1 decode failed (%d)", got);
            }
            if (!packet.sz && got == DAV1D_ERR(EAGAIN)) break;
            if (sent == DAV1D_ERR(EAGAIN) && got == DAV1D_ERR(EAGAIN))
                rt_fatal("codec: AV1 decoder made no progress");
        }
        dav1d_data_unref(&packet);
        if (av1_picture.data[0]) {
            if (av1_picture.p.bpc != 8 || av1_picture.p.layout != DAV1D_PIXEL_LAYOUT_I420)
                rt_fatal("codec: AV1 output requires an unimplemented pixel conversion (depth %d, layout %d)",
                         av1_picture.p.bpc, av1_picture.p.layout);
            av1_view.d_w = av1_picture.p.w;
            av1_view.d_h = av1_picture.p.h;
            for (int plane = 0; plane < 3; plane++) {
                av1_view.planes[plane] = av1_picture.data[plane];
                av1_view.stride[plane] = (int)av1_picture.stride[plane != 0];
            }
            img = &av1_view;
            pts = av1_picture.m.timestamp;
        }
    }
    if (d->vpx_ok && data && size) {
        if (vpx_codec_decode(&d->vpx, data, (unsigned)size, NULL, 0) != VPX_CODEC_OK)
            LOG_FIRST("codec: VP9 packet of %zu bytes failed: %s", size, vpx_codec_error_detail(&d->vpx));
        vpx_codec_iter_t it = NULL;
        while ((f = vpx_codec_get_frame(&d->vpx, &it))) img = f;   // a superframe shows at most one; keep the last
    }
    int filled = 1;
    if (img) put_picture(s, img), copy_slot(&d->last, s);
    else if (end && d->last.nv12) copy_slot(s, &d->last);
    else if (end) {
        vpx_image_t black = {.d_w = 16, .d_h = 16};
        static uint8_t y[16 * 16], uv[8 * 8];
        if (!uv[0]) memset(y, 16, sizeof y), memset(uv, 128, sizeof uv);
        black.planes[0] = y, black.planes[1] = black.planes[2] = uv, black.stride[0] = 16, black.stride[1] = black.stride[2] = 8;
        put_picture(s, &black);
    } else filled = 0;
    TRACE("decode %zu bytes pts %lld%s: buffer %d %s", size, (long long)pts, end ? " end" : "", (int)(s - d->slot),
          filled ? "filled" : "still waiting (no picture shown)");
    if (av1_picture.data[0]) dav1d_picture_unref(&av1_picture);
    LOG_FIRST("codec: first %s packet: %zu bytes, picture %ux%u", d->av1 ? "AV1" : "VP9", size, s->w, s->h);
    int n = 0;
    if (filled) {
        s->state = S_FILLED, s->pts = pts, s->eos = end;
        for (int k = 0; k < WAITERS; k++)
            if (s->waiter[k]) wake[n++] = s->waiter[k];
        memset(s->waiter, 0, sizeof s->waiter);
    }
    return n;
}

// Result nn::codec::video::Initialize(), Finalize(): nothing to open on the host
static void ov_video_init(Cpu *c) { ret_x(c, 0); }
static void ov_video_fini(Cpu *c) { ret_x(c, 0); }

static void decoder_init(Cpu *c, uint64_t key, unsigned w, unsigned h, int av1) {
    TRACE("initialize %s decoder %#llx %ux%u", av1 ? "AV1" : "VP9", (unsigned long long)key, w, h);
    plat_mutex_lock(&lock);
    Dec *d = dec_of(key);
    if (!d) d = dec_of(0);
    if (!d) rt_fatal("codec: more than %d VP9 decoders", DECODERS);
    if (d->vpx_ok) vpx_codec_destroy(&d->vpx);
    if (d->av1) dav1d_close(&d->av1);
    for (int i = 0; i < SLOTS; i++) free(d->slot[i].nv12);
    free(d->last.nv12);
    queue_drop(d);
    memset(d, 0, sizeof *d);
    d->key = key;
    if (av1) {
        Dav1dSettings settings;
        dav1d_default_settings(&settings);
        settings.n_threads = 2;
        settings.max_frame_delay = 1; // guest fences expect submission to make its picture available
        int result = dav1d_open(&d->av1, &settings);
        if (result < 0) rt_fatal("codec: dav1d initialization failed (%d)", result);
    } else {
        vpx_codec_dec_cfg_t cfg = {.threads = 2, .w = w, .h = h};
        d->vpx_ok = vpx_codec_dec_init(&d->vpx, vpx_codec_vp9_dx(), &cfg, 0) == VPX_CODEC_OK;
        if (!d->vpx_ok) rt_fatal("codec: libvpx initialization failed");
    }
    plat_mutex_unlock(&lock);
    rt_log("codec: %s decoder %#llx %ux%u on the host (%s)", av1 ? "AV1" : "VP9", (unsigned long long)key, w, h,
           av1 ? "dav1d" : "libvpx");
    ret_x(c, 0);
}
// Result InitializeVp9Decoder(Vp9DecoderType *, void *work, size_t, size_t, u16 w, u16 h, u32, input, output fmt)
static void ov_vp9_init(Cpu *c) { decoder_init(c, arg_x(c, 0), arg_x(c, 4) & 0xffff, arg_x(c, 5) & 0xffff, 0); }
// Result InitializeVp9Decoder(Vp9DecoderType *, size_t, size_t, u16 w, u16 h, u32, input, output fmt)
static void ov_vp9_init_nowork(Cpu *c) { decoder_init(c, arg_x(c, 0), arg_x(c, 3) & 0xffff, arg_x(c, 4) & 0xffff, 0); }
static void ov_av1_init(Cpu *c) { decoder_init(c, arg_x(c, 0), arg_x(c, 4) & 0xffff, arg_x(c, 5) & 0xffff, 1); }
static void ov_av1_init_remote(Cpu *c) { decoder_init(c, arg_x(c, 0), arg_x(c, 2) & 0xffff, arg_x(c, 3) & 0xffff, 1); }

// Result FinalizeVp9Decoder(Vp9DecoderType *)
static void ov_vp9_fini(Cpu *c) {
    plat_mutex_lock(&lock);
    Dec *d = dec_of(arg_x(c, 0));
    if (d) {
        if (d->vpx_ok) vpx_codec_destroy(&d->vpx);
        if (d->av1) dav1d_close(&d->av1);
        for (int i = 0; i < SLOTS; i++) free(d->slot[i].nv12);
        free(d->last.nv12);
        queue_drop(d);
        memset(d, 0, sizeof *d);
    }
    plat_mutex_unlock(&lock);
    ret_x(c, 0);
}

// Result FlushVp9Decoder(Vp9DecoderType *): discard queued input, retaining
// completed client-owned output images and their signalled fences until Release.
// Eglantine nx2_gsv.h INx2VideoSession::Flush follows the same ownership rule.
static void ov_vp9_flush(Cpu *c) {
    plat_mutex_lock(&lock);
    Dec *d = dec_of(arg_x(c, 0));
    if (d) queue_drop(d);
    if (d && d->av1) dav1d_flush(d->av1);
    plat_mutex_unlock(&lock);
    TRACE("flush");
    ret_x(c, 0);
}

// Result Start/StopVp9Decoder(Vp9DecoderType *), FinalizeDecoderImagePool(pool): nothing to do
static void ov_ok(Cpu *c) { ret_x(c, 0); }

// Result RegisterVp9DecoderBuffer(Vp9DecoderType *, u32 index, VideoDecoderImagePoolType *, u32)
static void ov_vp9_register(Cpu *c) {
    uint32_t i = (uint32_t)arg_x(c, 1);
    plat_mutex_lock(&lock);
    Dec *d = dec_of(arg_x(c, 0));
    if (d && i < SLOTS) d->slot[i].pool = arg_x(c, 2), d->slot[i].state = S_FREE;
    plat_mutex_unlock(&lock);
    if (!d || i >= SLOTS) rt_log("codec: RegisterVp9DecoderBuffer index %u of an unknown decoder or past %d", i, SLOTS);
    ret_x(c, 0);
}

// Result InitializeDecoderImagePool(pool, void *, size_t, const VideoDecoderImagePreference &, u32, CodecMode): the
// size the player reads back at +0x20 / +0x22
static void ov_pool_init(Cpu *c) {
    uint8_t *pool = arg_p(c, 0);
    const uint8_t *pref = arg_p(c, 3);
    uint16_t w, h;
    memcpy(&w, pref + 8, 2), memcpy(&h, pref + 10, 2);
    w++, h++;
    memcpy(pool + 0x20, &w, 2), memcpy(pool + 0x22, &h, 2);
    ret_x(c, 0);
}

// Result CalculateDecoderImagePoolBuffer(size_t *size, size_t *align, const preference &, u32 count),
// CalculateVp9DecoderWorkBuffer(size_t *size, size_t *align, size_t, u16 w, u16 h): the buffers hold nothing on the
// host (the pictures are host memory), so one page each
static void ov_calc_size(Cpu *c) {
    *(uint64_t *)arg_p(c, 0) = 0x1000;
    *(uint64_t *)arg_p(c, 1) = 0x1000;
    ret_x(c, 0);
}

// A guest SystemEventType (manual clear) standing for the game object at `key`: the same one for the same object, so
// movie after movie reuses the events instead of filling the kernel's table of bound events. Guest thread only.
// ponytail: 64 objects, linear scan; the player has one decoder and 15 sync point events.
static uint64_t event_for(Cpu *c, uint64_t key) {
    static struct { uint64_t key, ev; } tab[64];
    static int n;
    static PlatMutex tlock = PLAT_MUTEX_INIT;
    plat_mutex_lock(&tlock);
    uint64_t ev = 0;
    for (int i = 0; i < n && !ev; i++)
        if (tab[i].key == key) ev = tab[i].ev;
    if (!ev) {
        if (n == 64) rt_fatal("codec: more than 64 decoder and sync point objects");
        ev = (uint64_t)(uintptr_t)mem_kernel_alloc(0x100, 16);
        tab[n].key = key, tab[n++].ev = ev;
    }
    plat_mutex_unlock(&tlock);
    kern_bind_system_event(c, ev, 0);   // once per event; leaves the event's handles in x0-x2
    return ev;
}

// Result GetVp9DecoderSubmissionReadyEvent(nn::os::SystemEventType **out, Vp9DecoderType *): signalled while the
// decoder can take a packet, which is when an output buffer is reserved for its picture. The player clears it after a
// submission comes back not ready, so AcquireVp9DecoderOutputBuffer signals it again (ov_vp9_acquire).
static void ov_vp9_ready_event(Cpu *c) {
    uint64_t *out = arg_p(c, 0), dec = arg_x(c, 1);
    uint64_t ev = event_for(c, dec);
    kern_signal_system_event(ev);
    *out = ev;
    TRACE("submission-ready event %#llx handed out (signalled)", (unsigned long long)ev);
    ret_x(c, 0);
}

// The newer AV1 SDK returns the event pointer directly, without an out argument.
static void ov_av1_ready_event(Cpu *c) {
    uint64_t ev = event_for(c, arg_x(c, 0));
    kern_signal_system_event(ev);
    ret_x(c, ev);
}

static void ov_decoder_unregister(Cpu *c) {
    plat_mutex_lock(&lock);
    Dec *d = dec_of(arg_x(c, 0));
    unsigned i = (unsigned)arg_x(c, 1);
    if (d && i < SLOTS) {
        free(d->slot[i].nv12);
        memset(&d->slot[i], 0, sizeof d->slot[i]);
    }
    plat_mutex_unlock(&lock);
    ret_x(c, d && i < SLOTS ? 0 : R_NOT_READY);
}

// Result SubmitVp9DecoderInputBuffer(u64 *id, Vp9DecoderType *, const void *data, size_t size, TimeSpan pts, bool end):
// decoded at once into the oldest waiting buffer, else queued for the next one reserved; "not ready" once QUEUED
// packets wait. After the end of a guide movie the player flushes and starts over with the buffers it still holds,
// submitting its third packet before it releases one: without the queue that packet was refused, nothing released a
// buffer again, and the window kept the movie's first picture, a flat yellow card.
static void ov_vp9_submit(Cpu *c) {
    uint64_t *id = arg_p(c, 0);
    const uint8_t *data = arg_p(c, 2);
    size_t size = arg_x(c, 3);
    int64_t pts = (int64_t)arg_x(c, 4);
    int end = (int)(arg_x(c, 5) & 1);
    plat_mutex_lock(&lock);
    Dec *d = dec_of(arg_x(c, 1));
    Slot *s = d && !d->qn ? oldest_wait(d) : NULL;
    if (!s) {
        int queued = d && d->qn < QUEUED;
        if (queued) {
            Packet *q = &d->queue[(d->qhead + d->qn++) % QUEUED];
            *q = (Packet){size ? malloc(size) : NULL, size, pts, end};
            if (size && !q->data) rt_fatal("codec: out of memory for a %zu-byte packet", size);
            if (size) memcpy(q->data, data, size);
            if (id) *id = d->seq;
        }
        int waiting = d ? d->qn : 0;
        plat_mutex_unlock(&lock);
        TRACE("submit %zu bytes pts %lld%s: %s (%d queued)", size, (long long)pts, end ? " end" : "",
              queued ? "queued for the next reserved buffer" : "not ready", waiting);
        ret_x(c, queued ? 0 : R_NOT_READY);
        return;
    }
    uint64_t wake[WAITERS];
    int n = decode_into(d, s, data, size, pts, end, wake);
    if (id) *id = d->seq;
    plat_mutex_unlock(&lock);
    for (int k = 0; k < n; k++) kern_signal_system_event(wake[k]);
    ret_x(c, 0);
}

// Result AcquireVp9DecoderOutputBuffer(u32 *index, NativeSyncHandle *fence, Vp9DecoderType *): reserves a free buffer
// for the next picture, decodes queued packets into the waiting buffers; the fence carries the token
// RequestSyncPointEvent waits on
static void ov_vp9_acquire(Cpu *c) {
    uint32_t *index = arg_p(c, 0), *fence = arg_p(c, 1);
    uint64_t key = arg_x(c, 2);
    uint64_t wake[SLOTS * WAITERS];
    int n = 0;
    plat_mutex_lock(&lock);
    Dec *d = dec_of(key);
    int got = -1;
    for (int i = 0; d && i < SLOTS && got < 0; i++)
        if (d->slot[i].pool && d->slot[i].state == S_FREE) got = i;
    if (got >= 0) {
        Slot *s = &d->slot[got];
        s->state = S_WAIT, s->seq = d->seq++, s->eos = 0;
        memset(s->waiter, 0, sizeof s->waiter);
        *index = (uint32_t)got;
        if (fence) *fence = FENCE_TAG | (uint32_t)(d - decs) << 8 | (uint32_t)got;
        Slot *w;
        while (d->qn && (w = oldest_wait(d)) && n <= SLOTS * WAITERS - WAITERS) {
            Packet q = d->queue[d->qhead];
            d->qhead = (d->qhead + 1) % QUEUED, d->qn--;
            n += decode_into(d, w, q.data, q.size, q.pts, q.end, wake + n);
            free(q.data);
        }
    }
    plat_mutex_unlock(&lock);
    if (got < 0) rt_log("codec: AcquireVp9DecoderOutputBuffer with every registered buffer reserved");
    else TRACE("acquire: buffer %d", got);
    for (int k = 0; k < n; k++) kern_signal_system_event(wake[k]);
    // A reserved buffer lets the next packet in: wake a player that waits for the submission-ready event after a not
    // ready submission. Without this, the tutorial's guide movies stopped at their second picture.
    if (got >= 0) kern_signal_system_event(event_for(c, key));
    ret_x(c, got < 0 ? R_NOT_READY : 0);
}

// Result ReleaseVp9DecoderOutputBuffer(Vp9DecoderType *, u32 index, NativeSyncHandle)
static void ov_vp9_release(Cpu *c) {
    uint32_t i = (uint32_t)arg_x(c, 1);
    plat_mutex_lock(&lock);
    Dec *d = dec_of(arg_x(c, 0));
    if (d && i < SLOTS && d->slot[i].state != S_FREE) d->slot[i].state = S_FREE;
    plat_mutex_unlock(&lock);
    TRACE("release: buffer %u", i);
    ret_x(c, 0);
}

// Result GetVp9DecoderOutputBufferProperties(u16 *w, u16 *h, u16 *, u16 *, nn::movie::ColorSpace *, TimeSpan *pts,
// bool *end, Vp9DecoderType *, u32 index). The two unnamed u16 get the picture size too (aligned or display size).
static void ov_vp9_props(Cpu *c) {
    uint32_t i = (uint32_t)arg_x(c, 8);
    plat_mutex_lock(&lock);
    Dec *d = dec_of(arg_x(c, 7));
    Slot s = d && i < SLOTS ? d->slot[i] : (Slot){0};
    plat_mutex_unlock(&lock);
    for (int k = 0; k < 4; k++) {
        uint16_t *p = arg_p(c, k);
        if (p) *p = k & 1 ? s.h : s.w;
    }
    LOG_FIRST("codec: output properties: %ux%u", s.w, s.h);
    if (arg_p(c, 4)) *(uint32_t *)arg_p(c, 4) = 0;
    if (arg_p(c, 5)) *(int64_t *)arg_p(c, 5) = s.pts;
    if (arg_p(c, 6)) *(uint8_t *)arg_p(c, 6) = (uint8_t)s.eos;
    ret_x(c, d ? 0 : R_NOT_READY);
}

// AV1 omits the ColorSpace output: pts, eos, decoder and index shift down one.
static void ov_av1_props(Cpu *c) {
    unsigned i = (unsigned)arg_x(c, 7);
    plat_mutex_lock(&lock);
    Dec *d = dec_of(arg_x(c, 6));
    int valid = d && i < SLOTS && d->slot[i].state == S_FILLED;
    Slot s = valid ? d->slot[i] : (Slot){0};
    plat_mutex_unlock(&lock);
    if (!valid) { ret_x(c, R_NOT_READY); return; }
    for (int k = 0; k < 4; k++)
        if (arg_p(c, k)) *(uint16_t *)arg_p(c, k) = k & 1 ? s.h : s.w;
    if (arg_p(c, 4)) *(int64_t *)arg_p(c, 4) = s.pts;
    if (arg_p(c, 5)) *(uint8_t *)arg_p(c, 5) = (uint8_t)s.eos;
    TRACE("AV1 output properties: buffer %u %ux%u pts %lld", i, s.w, s.h, (long long)s.pts);
    ret_x(c, 0);
}

// Host lifecycle regression, including the newer AV1 properties ABI. No game data.
static void ov_sp_point_trywait(Cpu *c);
int probe_codec(void) {
    Cpu c = {0};
    uint64_t key = 0x1234;
    decoder_init(&c, key, 16, 16, 1);
    Dec *d = dec_of(key);
    if (!d || !d->av1 || d->vpx_ok) return 1;
    uint32_t fence = FENCE_TAG | (unsigned)(d - decs) << 8;
    d->slot[0].state = S_WAIT;
    c.x[0] = (uintptr_t)&fence;
    ov_sp_point_trywait(&c);
    if (c.x[0]) return 1;
    uint16_t dimensions[4] = {0};
    int64_t pts = -1;
    uint8_t end = 0;
    d->slot[0].state = S_FILLED;
    d->slot[0].w = 16; d->slot[0].h = 12;
    d->slot[0].pts = 123456789; d->slot[0].eos = 1;
    c.x[0] = (uintptr_t)&fence;
    ov_sp_point_trywait(&c);
    if (c.x[0] != 1) return 1;
    for (int k = 0; k < 4; k++) c.x[k] = (uintptr_t)&dimensions[k];
    c.x[4] = (uintptr_t)&pts; c.x[5] = (uintptr_t)&end; c.x[6] = key; c.x[7] = 0;
    ov_av1_props(&c);
    if (c.x[0] || dimensions[0] != 16 || dimensions[1] != 12 || dimensions[2] != 16 ||
        dimensions[3] != 12 || pts != 123456789 || end != 1) return 1;
    // Flush may discard queued input, but an already completed output belongs
    // to the client until Release. Its fence and properties must remain valid.
    d->slot[1].state = S_WAIT;
    d->queue[0] = (Packet){malloc(4), 4, 987, 0};
    if (!d->queue[0].data) return 1;
    d->qn = 1;
    c.x[0] = key;
    ov_vp9_flush(&c);
    c.x[0] = (uintptr_t)&fence;
    ov_sp_point_trywait(&c);
    if (c.x[0] != 1) { rt_log("codec probe: FAIL flush revoked a completed output fence"); return 1; }
    if (d->slot[1].state != S_WAIT || d->qn || d->qhead) return 1;
    memset(dimensions, 0, sizeof dimensions); pts = -1; end = 0;
    for (int k = 0; k < 4; k++) c.x[k] = (uintptr_t)&dimensions[k];
    c.x[4] = (uintptr_t)&pts; c.x[5] = (uintptr_t)&end; c.x[6] = key; c.x[7] = 0;
    ov_av1_props(&c);
    if (c.x[0] || dimensions[0] != 16 || dimensions[1] != 12 || pts != 123456789 || end != 1) return 1;
    c.x[0] = key;
    ov_vp9_fini(&c);
    if (dec_of(key)) return 1;
    decoder_init(&c, key, 16, 16, 0);
    d = dec_of(key);
    if (!d || !d->vpx_ok || d->av1) return 1;
    c.x[0] = key;
    ov_vp9_fini(&c);
    rt_log("codec probe: AV1/VP9 initialization, AV1 properties ABI, fence readiness, flush and finalization passed");
    return 0;
}

// Result ReadDecoderOutputImageNv12(const VideoDecoderImagePoolType *, u32 image, u16 x, u16 y, u16 w, u16 h,
// void *luma, size_t luma_pitch, size_t luma_size, void *chroma, size_t chroma_pitch, size_t chroma_size)
static void ov_read_nv12(Cpu *c) {
    uint64_t pool = arg_x(c, 0);
    uint32_t x0 = arg_x(c, 2) & 0xffff, y0 = arg_x(c, 3) & 0xffff, w = arg_x(c, 4) & 0xffff, h = arg_x(c, 5) & 0xffff;
    uint8_t *ly = arg_p(c, 6), *luv = arg_p(c, 9);
    size_t yp = arg_x(c, 7), ys = arg_x(c, 8), uvp = arg_x(c, 10), uvs = arg_x(c, 11);
    plat_mutex_lock(&lock);
    const Slot *s = NULL;
    for (int k = 0; k < DECODERS && !s; k++)
        for (int i = 0; decs[k].key && i < SLOTS && !s; i++)
            if (decs[k].slot[i].pool == pool && decs[k].slot[i].nv12) s = &decs[k].slot[i];
    if (s) {
        uint32_t cx = x0 < s->w ? x0 : s->w, cy = y0 < s->h ? y0 : s->h;
        uint32_t rw = w < s->w - cx ? w : s->w - cx, rh = h < s->h - cy ? h : s->h - cy;
        size_t n = rw < yp ? rw : yp;   // each row stays inside the caller's pitch and buffer
        for (uint32_t r = 0; r < rh && ly && r * yp + n <= ys; r++)
            memcpy(ly + r * yp, s->nv12 + (size_t)(cy + r) * s->w + cx, n);
        const uint8_t *uv = s->nv12 + (size_t)s->w * s->h;
        uint32_t uw = 2 * ((rw + 1) / 2), uh = (rh + 1) / 2, ux = 2 * (cx / 2), uy = cy / 2;
        n = uw < uvp ? uw : uvp;
        for (uint32_t r = 0; r < uh && luv && r * uvp + n <= uvs; r++)
            memcpy(luv + r * uvp, uv + (size_t)(uy + r) * 2 * cw(s->w) + ux, n);
    }
    int64_t pts = s ? s->pts : -1;
    plat_mutex_unlock(&lock);
    LOG_FIRST("codec: first NV12 read %ux%u (%s)", w, h, s ? "a decoded picture" : "no picture for this pool");
    TRACE("read pool %#llx: pts %lld", (unsigned long long)pool, (long long)pts);
    ret_x(c, 0);
}

// NativeImageHandle GetDecoderImagePoolNativeImageHandle(const VideoDecoderImagePoolType *, u32): no GPU image
static void ov_pool_image(Cpu *c) {
    LOG_FIRST("codec: GetDecoderImagePoolNativeImageHandle %p #%u: no GPU image (the player's NV12 path is served)",
              arg_p(c, 0), (unsigned)arg_x(c, 1));
    ret_x(c, 0);
}

// ---- nn::syncpt::sdk: GPU sync point events (the decoder's output fences), not in the SDK's loaded modules. Each is a
// guest system event; a request is signalled at once, as the host has no sync point to wait for.
// Result CreateSyncPointEvent(SyncPointEventType *)
static void ov_sp_create(Cpu *c) {
    event_for(c, arg_x(c, 0));
    ret_x(c, 0);
}
// void InitializeMultiWaitHolder(nn::os::MultiWaitHolderType *, SyncPointEventType *): the system event's holder
static void ov_sp_holder(Cpu *c) {
    static uint64_t init;
    if (!init && !(init = ldr_symbol("_ZN2nn2os25InitializeMultiWaitHolderEPNS0_19MultiWaitHolderTypeEPNS0_15SystemEventTypeE")))
        rt_fatal("codec: nn::os::InitializeMultiWaitHolder(SystemEventType *) is not loaded");
    uint64_t holder = arg_x(c, 0), ev = event_for(c, arg_x(c, 1));
    rt_call(c, init, 2, holder, ev);
}
// bool TryWaitSyncPointEvent(const SyncPointEventType *)
static void ov_sp_trywait(Cpu *c) {
    static uint64_t trywait;
    if (!trywait && !(trywait = ldr_symbol("_ZN2nn2os18TryWaitSystemEventEPNS0_15SystemEventTypeE")))
        rt_fatal("codec: nn::os::TryWaitSystemEvent is not loaded");
    uint64_t ev = event_for(c, arg_x(c, 0));
    ret_x(c, rt_call(c, trywait, 1, ev) & 1);
}
// The movie player also polls a fence directly, rather than its event. The SDK's
// driver callback table is not initialized when decoding on the host, so this
// entry must use the same completion state as RequestSyncPointEvent.
static void ov_sp_point_trywait(Cpu *c) {
    const uint32_t *handle = arg_p(c, 0);
    uint32_t token = handle ? *handle : 0;
    unsigned decoder = token >> 8 & 0xff, slot = token & 0xff;
    if ((token & 0xffff0000u) != FENCE_TAG || decoder >= DECODERS || slot >= SLOTS)
        rt_fatal("codec: TryWaitSyncPoint received an unsupported fence %#x", token);
    plat_mutex_lock(&lock);
    int ready = decs[decoder].key && decs[decoder].slot[slot].state == S_FILLED;
    plat_mutex_unlock(&lock);
    ret_x(c, ready);
}
static void clear_event(Cpu *c, uint64_t ev) {
    static uint64_t clear;
    if (!clear && !(clear = ldr_symbol("_ZN2nn2os16ClearSystemEventEPNS0_15SystemEventTypeE")))
        rt_fatal("codec: nn::os::ClearSystemEvent is not loaded");
    rt_call(c, clear, 1, ev);
}

// void RequestSyncPointEvent(SyncPointEventType *, const SyncPointHandle &): re-arms the event (cleared, as the last
// request may have left it signalled); a decoder fence (FENCE_TAG) fires when its buffer holds a picture, anything
// else at once, as the host has no sync point to wait for
static void ov_sp_request(Cpu *c) {
    const uint32_t *h = arg_p(c, 1);
    uint32_t tok = h ? *h : 0;
    uint64_t ev = event_for(c, arg_x(c, 0));
    clear_event(c, ev);
    int now = 1;
    if ((tok & 0xffff0000u) == FENCE_TAG && (tok >> 8 & 0xff) < DECODERS && (tok & 0xff) < SLOTS) {
        plat_mutex_lock(&lock);
        Slot *s = &decs[tok >> 8 & 0xff].slot[tok & 0xff];
        if (s->state == S_WAIT)
            for (int k = 0; k < WAITERS; k++)
                if (!s->waiter[k] || s->waiter[k] == ev) {
                    s->waiter[k] = ev, now = 0;
                    break;
                }
        plat_mutex_unlock(&lock);
    }
    TRACE("sync point request %#x: %s", tok, now ? "signalled at once" : "waits for its picture");
    if (now) kern_signal_system_event(ev);
}
// void CancelSyncPointEvent(SyncPointEventType *): the request is dropped and the event cleared
static void ov_sp_cancel(Cpu *c) {
    uint64_t ev = event_for(c, arg_x(c, 0));
    plat_mutex_lock(&lock);
    for (int k = 0; k < DECODERS; k++)
        for (int i = 0; i < SLOTS; i++)
            for (int j = 0; j < WAITERS; j++)
                if (decs[k].slot[i].waiter[j] == ev) decs[k].slot[i].waiter[j] = 0;
    plat_mutex_unlock(&lock);
    clear_event(c, ev);
}
// void DestroySyncPointEvent(SyncPointEventType *): the event stays bound for the next Create on the same object
static void ov_sp_nop(Cpu *c) { (void)c; }

HOST_OVERRIDE("_ZN2nn5codec5video10InitializeEv", ov_video_init);
// These signatures come from the supplied SDK's exported symbols; no title offsets.
HOST_OVERRIDE("_ZN2nn5codec36InitializeAv1DecoderByTransferMemoryEPNS0_14Av1DecoderTypeEPvmmttjNS0_23VideoDecoderInputFormatENS0_24VideoDecoderOutputFormatENS0_22VideoDecoderOutputModeE", ov_av1_init);
HOST_OVERRIDE("_ZN2nn5codec34InitializeAv1DecoderByRemoteMemoryEPNS0_14Av1DecoderTypeEmttjNS0_23VideoDecoderInputFormatENS0_24VideoDecoderOutputFormatENS0_22VideoDecoderOutputModeE", ov_av1_init_remote);
HOST_OVERRIDE("_ZN2nn5codec18FinalizeAv1DecoderEPNS0_14Av1DecoderTypeE", ov_vp9_fini);
HOST_OVERRIDE("_ZN2nn5codec15StartAv1DecoderEPNS0_14Av1DecoderTypeE", ov_ok);
HOST_OVERRIDE("_ZN2nn5codec14StopAv1DecoderEPNS0_14Av1DecoderTypeE", ov_ok);
HOST_OVERRIDE("_ZN2nn5codec15FlushAv1DecoderEPNS0_14Av1DecoderTypeE", ov_vp9_flush);
HOST_OVERRIDE("_ZN2nn5codec24RegisterAv1DecoderBufferEPNS0_14Av1DecoderTypeEjPNS0_25VideoDecoderImagePoolTypeEj", ov_vp9_register);
HOST_OVERRIDE("_ZN2nn5codec26UnregisterAv1DecoderBufferEPNS0_14Av1DecoderTypeEj", ov_decoder_unregister);
HOST_OVERRIDE("_ZN2nn5codec33GetAv1DecoderSubmissionReadyEventEPNS0_14Av1DecoderTypeE", ov_av1_ready_event);
HOST_OVERRIDE("_ZN2nn5codec27SubmitAv1DecoderInputBufferEPmPNS0_14Av1DecoderTypeEPKvmNS_8TimeSpanEb", ov_vp9_submit);
HOST_OVERRIDE("_ZN2nn5codec29AcquireAv1DecoderOutputBufferEPjPNS_2gs16NativeSyncHandleEPNS0_14Av1DecoderTypeE", ov_vp9_acquire);
HOST_OVERRIDE("_ZN2nn5codec29ReleaseAv1DecoderOutputBufferEPNS0_14Av1DecoderTypeEjNS_2gs16NativeSyncHandleE", ov_vp9_release);
HOST_OVERRIDE("_ZN2nn5codec35GetAv1DecoderOutputBufferPropertiesEPtS1_S1_S1_PNS_8TimeSpanEPbPNS0_14Av1DecoderTypeEj", ov_av1_props);
HOST_OVERRIDE("_ZN2nn5codec26InitializeDecoderImagePoolEPNS0_25VideoDecoderImagePoolTypeEPvmRKNS0_27VideoDecoderImagePreferenceEj", ov_pool_init);
HOST_OVERRIDE("_ZN2nn5codec5video8FinalizeEv", ov_video_fini);
HOST_OVERRIDE("_ZN2nn5codec20InitializeVp9DecoderEPNS0_14Vp9DecoderTypeEPvmmttjNS0_23VideoDecoderInputFormatENS0_"
              "24VideoDecoderOutputFormatE", ov_vp9_init);
HOST_OVERRIDE("_ZN2nn5codec20InitializeVp9DecoderEPNS0_14Vp9DecoderTypeEmmttjNS0_23VideoDecoderInputFormatENS0_"
              "24VideoDecoderOutputFormatE", ov_vp9_init_nowork);
HOST_OVERRIDE("_ZN2nn5codec18FinalizeVp9DecoderEPNS0_14Vp9DecoderTypeE", ov_vp9_fini);
HOST_OVERRIDE("_ZN2nn5codec15StartVp9DecoderEPNS0_14Vp9DecoderTypeE", ov_ok);
HOST_OVERRIDE("_ZN2nn5codec14StopVp9DecoderEPNS0_14Vp9DecoderTypeE", ov_ok);
HOST_OVERRIDE("_ZN2nn5codec15FlushVp9DecoderEPNS0_14Vp9DecoderTypeE", ov_vp9_flush);
HOST_OVERRIDE("_ZN2nn5codec24RegisterVp9DecoderBufferEPNS0_14Vp9DecoderTypeEjPNS0_25VideoDecoderImagePoolTypeEj",
              ov_vp9_register);
HOST_OVERRIDE("_ZN2nn5codec26InitializeDecoderImagePoolEPNS0_25VideoDecoderImagePoolTypeEPvmRKNS0_27VideoDecoderImage"
              "PreferenceEjNS0_9CodecModeE", ov_pool_init);
HOST_OVERRIDE("_ZN2nn5codec24FinalizeDecoderImagePoolEPNS0_25VideoDecoderImagePoolTypeE", ov_ok);
HOST_OVERRIDE("_ZN2nn5codec31CalculateDecoderImagePoolBufferEPmS1_RKNS0_27VideoDecoderImagePreferenceEj", ov_calc_size);
HOST_OVERRIDE("_ZN2nn5codec29CalculateVp9DecoderWorkBufferEPmS1_mtt", ov_calc_size);
HOST_OVERRIDE("_ZN2nn5codec33GetVp9DecoderSubmissionReadyEventEPPNS_2os15SystemEventTypeEPNS0_14Vp9DecoderTypeE",
              ov_vp9_ready_event);
HOST_OVERRIDE("_ZN2nn5codec27SubmitVp9DecoderInputBufferEPmPNS0_14Vp9DecoderTypeEPKvmNS_8TimeSpanEb", ov_vp9_submit);
HOST_OVERRIDE("_ZN2nn5codec29AcquireVp9DecoderOutputBufferEPjPNS_2gs16NativeSyncHandleEPNS0_14Vp9DecoderTypeE",
              ov_vp9_acquire);
HOST_OVERRIDE("_ZN2nn5codec29ReleaseVp9DecoderOutputBufferEPNS0_14Vp9DecoderTypeEjNS_2gs16NativeSyncHandleE",
              ov_vp9_release);
HOST_OVERRIDE("_ZN2nn5codec35GetVp9DecoderOutputBufferPropertiesEPtS1_S1_S1_PNS_5movie10ColorSpaceEPNS_8TimeSpanEPbPNS0_"
              "14Vp9DecoderTypeEj", ov_vp9_props);
HOST_OVERRIDE("_ZN2nn5codec26ReadDecoderOutputImageNv12EPKNS0_25VideoDecoderImagePoolTypeEjttttPvmmS4_mm", ov_read_nv12);
HOST_OVERRIDE("_ZN2nn5codec36GetDecoderImagePoolNativeImageHandleEPKNS0_25VideoDecoderImagePoolTypeEj", ov_pool_image);
HOST_OVERRIDE("_ZN2nn6syncpt3sdk20CreateSyncPointEventEPNS1_18SyncPointEventTypeE", ov_sp_create);
HOST_OVERRIDE("_ZN2nn6syncpt3sdk25InitializeMultiWaitHolderEPNS_2os19MultiWaitHolderTypeEPNS1_18SyncPointEventTypeE",
              ov_sp_holder);
HOST_OVERRIDE("_ZN2nn6syncpt3sdk21TryWaitSyncPointEventEPKNS1_18SyncPointEventTypeE", ov_sp_trywait);
HOST_OVERRIDE("_ZN2nn6syncpt3sdk16TryWaitSyncPointERKNS1_15SyncPointHandleE", ov_sp_point_trywait);
HOST_OVERRIDE("_ZN2nn6syncpt3sdk21RequestSyncPointEventEPNS1_18SyncPointEventTypeERKNS1_15SyncPointHandleE",
              ov_sp_request);
HOST_OVERRIDE("_ZN2nn6syncpt3sdk20CancelSyncPointEventEPNS1_18SyncPointEventTypeE", ov_sp_cancel);
HOST_OVERRIDE("_ZN2nn6syncpt3sdk21DestroySyncPointEventEPNS1_18SyncPointEventTypeE", ov_sp_nop);
