/* Regression scenarios against actual nn_audio.c calls; authored buffers only. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
typedef struct { uint64_t x[32]; } Ctx;
static _Alignas(8) uint8_t guest[4096];
static int failures;
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL:%d %s\n", __LINE__, #x); failures++; } } while (0)
#define GP(a) (guest + (a))
#define G64(a) (*(uint64_t *)GP(a))
#define G32(a) (*(uint32_t *)GP(a))
#define ARG(n) (c->x[n])
#define RET(v) (c->x[0] = (uint64_t)(v))
#define HLE(sym) void imp_##sym(Ctx *c)
#define AUT(...) ((void)0)
static int diag_on = 1, diag_events;
static char diag_kind[64], diag_detail[400];
static int ocr_diag_enabled(void) { return diag_on; }
static void ocr_diag_event(const char *kind, const char *detail) {
    ++diag_events;
    snprintf(diag_kind, sizeof diag_kind, "%s", kind);
    snprintf(diag_detail, sizeof diag_detail, "%s", detail);
}
#define env_on(name) 0
static void hos_log(const char *format, ...) { (void)format; }
static void au_lock(void) {}
static void au_unlock(void) {}
static const char *fixture_getenv(const char *name) { (void)name; return NULL; }
#define getenv fixture_getenv
#include "actual_music_stop.inc"

#define APPEND imp__ZN2nn5audio16AppendWaveBufferEPNS0_9VoiceTypeEPKNS0_10WaveBufferE
#define RELEASED imp__ZN2nn5audio21GetReleasedWaveBufferEPNS0_9VoiceTypeE
#define COUNT imp__ZN2nn5audio18GetWaveBufferCountEPKNS0_9VoiceTypeE
#define STATE imp__ZN2nn5audio17SetVoicePlayStateEPNS0_9VoiceTypeENS1_9PlayStateE
#define PLAYED imp__ZN2nn5audio25GetVoicePlayedSampleCountEPKNS0_9VoiceTypeE
enum { OBJECT = 0x40, BUFFER = 0x200, NEXT_BUFFER = 0x240, SAMPLES = 0x400, LENGTH = 64 };
static uint64_t call(void (*fn)(Ctx *), int voice, uint64_t a1) {
    Ctx c = {0}; c.x[0] = OBJECT + (uint64_t)voice * 16; c.x[1] = a1; fn(&c); return c.x[0];
}
static void reset(void) {
    memset(guest, 0, sizeof guest); memset(voices, 0, sizeof voices); memset(mixes, 0, sizeof mixes); ncmds = 0;
    mixes[0].used = 1; mixes[0].buffers = 1;
    for (int b = BUFFER; b <= NEXT_BUFFER; b += 0x40) {
        G64(b) = SAMPLES; G64(b + 8) = LENGTH * 2;
        G32(b + 0x10) = 0; G32(b + 0x14) = LENGTH;
    }
    guest[BUFFER + 0x18] = 1; /* a looping music buffer */
    for (int i = 0; i < 6; i++) {
        Voice *v = &voices[i];
        v->used = 1; v->channels = 1; v->format = FMT_PCM16; v->rate = RATE; v->state = PLAY_STOPPED;
        v->volume = 1; v->pitch = 1; v->dest_kind = DEST_MIX; v->dest = 0; v->vol[0][0] = 1;
        put_handle(OBJECT + (uint64_t)i * 16, K_VOICE, i);
    }
}
static void consume(int voice, int samples) {
    for (int i = 0; i < samples; i++) CHECK(next_source_frame(&voices[voice]));
}
static void start(int voice) {
    CHECK(call(APPEND, voice, BUFFER)); call(STATE, voice, PLAY_STARTED); commit();
}

int main(void) {
    /* Cancel music while primed but not playing. It must never resurrect on Start. */
    reset(); CHECK(call(APPEND, 0, BUFFER)); call(STATE, 0, PLAY_STOPPED); commit();
    CHECK(call(COUNT, 0, 0) == 0); CHECK(call(RELEASED, 0, 0) == BUFFER);
    call(STATE, 0, PLAY_STARTED); commit(); CHECK(!next_source_frame(&voices[0]));
    render_voice(&voices[0]);
    for (int i = 0; i < FRAME; i++) CHECK(mixes[0].buf[0][i] == 0); /* cancelled loop is silent */

    /* A real stop resets time, even if Start reuses this voice in the same update. */
    reset(); start(0); consume(0, 123); commit(); CHECK(call(PLAYED, 0, 0) == 123);
    call(STATE, 0, PLAY_STOPPED); CHECK(call(PLAYED, 0, 0) == 123); commit();
    CHECK(call(PLAYED, 0, 0) == 0); CHECK(call(COUNT, 0, 0) == 0);
    CHECK(call(RELEASED, 0, 0) == BUFFER); CHECK(!call(RELEASED, 0, 0));
    start(0); consume(0, 7); commit(); CHECK(call(PLAYED, 0, 0) == 7);

    /* Stop, append a replacement, cancel it: a repeated stop must flush it too. */
    reset(); start(0); consume(0, 15);
    call(STATE, 0, PLAY_STOPPED); CHECK(call(APPEND, 0, NEXT_BUFFER));
    call(STATE, 0, PLAY_STOPPED); call(STATE, 0, PLAY_STARTED); commit();
    CHECK(call(COUNT, 0, 0) == 0); CHECK(call(PLAYED, 0, 0) == 0);
    CHECK(call(RELEASED, 0, 0) == BUFFER); CHECK(call(RELEASED, 0, 0) == NEXT_BUFFER);
    CHECK(!call(RELEASED, 0, 0)); CHECK(!next_source_frame(&voices[0]));

    /* A replacement appended AFTER the last stop must play normally. */
    reset(); start(0); consume(0, 19);
    call(STATE, 0, PLAY_STOPPED); CHECK(call(APPEND, 0, NEXT_BUFFER)); call(STATE, 0, PLAY_STARTED); commit();
    CHECK(call(COUNT, 0, 0) == 1); CHECK(call(PLAYED, 0, 0) == 0);
    consume(0, LENGTH); commit(); CHECK(call(PLAYED, 0, 0) == LENGTH);
    CHECK(!next_source_frame(&voices[0])); commit();
    CHECK(call(COUNT, 0, 0) == 0);
    CHECK(call(RELEASED, 0, 0) == BUFFER); CHECK(call(RELEASED, 0, 0) == NEXT_BUFFER);

    /* Pause/resume preserves both queued audio and playback position. */
    reset(); start(0); consume(0, 23); commit();
    call(STATE, 0, PLAY_PAUSED); commit();
    render_voice(&voices[0]); commit();
    CHECK(call(COUNT, 0, 0) == 1); CHECK(call(PLAYED, 0, 0) == 23); CHECK(!call(RELEASED, 0, 0));
    call(STATE, 0, PLAY_STARTED); commit(); consume(0, 5); commit();
    CHECK(call(PLAYED, 0, 0) == 28);

    /* The mixer runs between per-speaker queries. One update must report one snapshot. */
    reset(); for (int i = 0; i < 6; i++) start(i);
    for (int i = 0; i < 6; i++) consume(i, 12);
    commit(); CHECK(call(PLAYED, 0, 0) == 12);
    consume(1, 5); CHECK(call(PLAYED, 1, 0) == 12);
    commit(); CHECK(call(PLAYED, 1, 0) == 17); CHECK(call(PLAYED, 0, 0) == 12);
    call(STATE, 1, PLAY_STOPPED); commit();
    CHECK(call(PLAYED, 1, 0) == 0); CHECK(call(PLAYED, 0, 0) == 12);
    CHECK(call(COUNT, 0, 0) == 1); /* no global audio reset */

    /* A game-thread stall can trigger the mixer's 50 ms fallback between the
       game's per-speaker queries. It may apply pending controls, but must not
       publish a new status snapshot halfway through those queries. */
    reset();
    guest[BUFFER + 0x18] = 0;
    for (int i = 0; i < 6; i++) start(i);
    for (int i = 0; i < 6; i++) consume(i, 12);
    commit();
    CHECK(call(PLAYED, 0, 0) == 12 && call(COUNT, 0, 0) == 1);
    for (int i = 1; i < 6; i++) {
        consume(i, LENGTH - 12);
        CHECK(!next_source_frame(&voices[i]));
    }
    call(STATE, 5, PLAY_STOPPED); /* still applied while the client is stalled */
    timeout_update();
    CHECK(voices[5].state == PLAY_STOPPED && ncmds == 0);
    for (int i = 1; i < 6; i++) {
        CHECK(call(PLAYED, i, 0) == 12);
        CHECK(call(COUNT, i, 0) == 1);
        CHECK(call(RELEASED, i, 0) == 0);
    }
    commit(); /* only the client's update publishes those changes */
    for (int i = 1; i < 6; i++) {
        CHECK(call(PLAYED, i, 0) == (i == 5 ? 0 : LENGTH));
        CHECK(call(COUNT, i, 0) == 0);
        CHECK(call(RELEASED, i, 0) == BUFFER);
        CHECK(call(RELEASED, i, 0) == 0);
    }
    CHECK(call(COUNT, 0, 0) == 1);
    /* Diagnostic snapshots describe looping/empty voices without consuming them,
       and are throttled; disabled diagnostics emit nothing. */
    reset(); start(0); consume(0, 12);
    const int before = diag_events;
    audio_status_diagnostic(10000000000LL);
    CHECK(diag_events == before + 1 && !strcmp(diag_kind, "audio_status"));
    CHECK(strstr(diag_detail, "voices=6 playing=1 looping=1 empty_playing=0"));
    CHECK(voices[0].played == 12 && voices[0].nwb == 1);
    audio_status_diagnostic(11000000000LL);
    CHECK(diag_events == before + 1);
    diag_on = 0; audio_status_diagnostic(20000000000LL);
    audio_voice_diagnostic("disabled", 0);
    CHECK(diag_events == before + 1);
    diag_on = 1; audio_voice_diagnostic("before_stop", 0);
    CHECK(strstr(diag_detail, "queued=1 pending=0 loop=1 played=12"));
    free(cmds);
    if (!failures) puts("PASS: loop cancellation, stop/restart ordering, pause and coherent six-channel status across mixer timeouts");
    return failures != 0;
}
