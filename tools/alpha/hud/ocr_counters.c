/* (Ocarina Reborn) the Classic counters row (F1 > Gameplay, live): as on the N64, no count over Link when he picks something up,
   and the rupees always in the bottom left corner.

   - The actual pickup layout is updated by f_80a87e50 independently of pouch_content_change. Mask its root alpha,
     leaving inventory events, timers and animations intact. The alpha setter hook also masks later animation writes.
     Verified layout chain: pickup vtable 0x84c0ac28, layout at +0x28; f_80229650(layout + 0x40) resolves the root as
     *( *(layout + 0x80) + 0x100 ). f_802f8ac0 sets root alpha (+0x74) and propagates its dirty flag to children.
   - The rupees: f_80a87c30(manager, 1) is how the game's own pick-up indicator (f_80a87e50, its +0x35c) reads the wallet: the
     game data int 0xc995bbb8 through the game data manager. The manager is *(*0x84c9e0d0), as the indicator takes it. Once
     every 10 frames, with the row on, the frame hook asks it and hands the count to the renderer (rx_option_set
     OCR_OPT_RUPEES, gpu/vk/vk_menu.cpp draw_rupees), -1 without a live player. The manager exists before loading a save!
   nx2/ocr_counters.py hooks the pickup update, root alpha setter and f_831f3200 (once a frame).
   Found with the UI diagnostics of 2026-11-13 (tools/alpha/hud/ocr_uidiag.*) and Hookshot's own notes on f_80a87e50
   (nx2/oot_patches.py WHOLE_SITES). */
#include "hos.h"
#include "ocr_tools.h"
#include <windows.h>
#include <string.h>

int rx_option(int id, int otherwise);
void rx_option_set(int id, int value);
int hos_oot_flight_shortcut_ready(void);   /* validated Link heartbeat, independent of the cheats switch */
extern void f_802f8ac0(Ctx *c);
enum { OCR_OPT_COUNTERS = 4083, OCR_OPT_RUPEES = 4084 };   /* (the same in vk_replay.cpp / vk_menu.cpp: engine_v21.py apply_counters) */

static int on(void) { return rx_option(OCR_OPT_COUNTERS, 0) == 1; }
static int photo(void) { return rx_option(OCR_OPT_PHOTO, 0) == 1; }
int hos_oot_story_event_active(void);

typedef struct { uint64_t owner, root; uint32_t alpha; int hidden; } Pickup;
static Pickup pickups[32];
static SRWLOCK pickup_lock = SRWLOCK_INIT;
static _Thread_local int setting_alpha;

/* Verified UI screen types; pause, inventory, dialogue and cutscene screens stay
   outside this list. All use the same layout root chain. */
static int photo_hud_vtable(uint64_t vt) {
    return vt == 0x84c08300ull /* minimap */ || vt == 0x84c0b710ull /* PlayerStatus */ ||
           vt == 0x84c0afe0ull /* PlayerStatus3D */ || vt == 0x84c07ec8ull /* location */ ||
           vt == 0x84c042e8ull; /* floating balloon messages */
}

static uint64_t pickup_root(Ctx *c, uint64_t owner) {
    if (!owner) return 0;
    const uint64_t vt = recomp_load64(c, owner);
    if (vt != 0x84c0ac28ull && !photo_hud_vtable(vt)) return 0;
    const uint64_t layout = recomp_load64(c, owner + 0x28);
    const uint64_t instance = layout ? recomp_load64(c, layout + 0x80) : 0;
    return instance ? recomp_load64(c, instance + 0x100) : 0;
}

static void set_alpha(Ctx *c, uint64_t root, uint32_t alpha) {
    const Ctx saved = *c;
    c->x[0] = root;
    c->x[30] = 0;
    memcpy(&c->vreg[0][0], &alpha, sizeof alpha);
    setting_alpha++;
    f_802f8ac0(c);   /* own setter: invalidates inherited child alpha too */
    setting_alpha--;
    *c = saved;
}

/* Before the pickup update's stack frame. Never skips the update. */
static void mask_layout(Ctx *c, uint64_t owner, int enabled) {
    const uint64_t root = pickup_root(c, owner);
    if (!root) return;
    const uint32_t current = (uint32_t)recomp_load32(c, root + 0x74);
    uint32_t alpha = current;
    int write = 0, logged = 0;
    AcquireSRWLockExclusive(&pickup_lock);
    Pickup *p = NULL, *empty = NULL;
    for (unsigned i = 0; i < sizeof pickups / sizeof pickups[0]; i++) {
        if (pickups[i].owner && pickup_root(c, pickups[i].owner) != pickups[i].root)
            memset(&pickups[i], 0, sizeof pickups[i]);
        if (pickups[i].owner == owner) { p = &pickups[i]; break; }
        if (!pickups[i].owner && !empty) empty = &pickups[i];
    }
    if (enabled) {
        if (!p) p = empty;
        if (p) {
            if (p->root != root || !p->hidden || current != 0) p->alpha = current;
            logged = !p->hidden || p->root != root;
            p->owner = owner, p->root = root, p->hidden = 1;
            alpha = 0, write = current != 0;
        }
    } else if (p) {
        if (p->root == root && p->hidden && current == 0) alpha = p->alpha, write = alpha != current;
        memset(p, 0, sizeof *p);
    }
    ReleaseSRWLockExclusive(&pickup_lock);
    if (write) set_alpha(c, root, alpha);
    if (logged) {
        static LONG lines;
        if (InterlockedIncrement(&lines) <= 8)
            hos_log("[OcarinaReborn/COUNTERS] UI layout masked (owner %#llx, root %#llx)",
                    (unsigned long long)owner, (unsigned long long)root);
    }
}

void ocr_counters_pickup(Ctx *c) { mask_layout(c, c->x[0], on() || photo()); }

/* The normal HUD's update still runs: hiding panes never skips game UI logic. */
void ocr_photo_hud(Ctx *c, uint64_t screen) {
    if (screen && photo_hud_vtable(recomp_load64(c, screen))) mask_layout(c, screen, photo());
}

/* After the alpha setter's first ldr s1, before its comparison: remember the
   animation's requested s0, but force 0 only on the verified pickup root. */
void ocr_counters_alpha(Ctx *c) {
    if (setting_alpha || (!on() && !photo())) return;
    AcquireSRWLockExclusive(&pickup_lock);
    for (unsigned i = 0; i < sizeof pickups / sizeof pickups[0]; i++) {
        Pickup *p = &pickups[i];
        if (p->hidden && p->root == c->x[0]) {
            const int is_pickup = recomp_load64(c, p->owner) == 0x84c0ac28ull;
            if (!(photo() || (is_pickup && on()))) break;
            if (pickup_root(c, p->owner) == p->root) {
                memcpy(&p->alpha, &c->vreg[0][0], sizeof p->alpha);
                const uint32_t zero = 0;
                memcpy(&c->vreg[0][0], &zero, sizeof zero);
            } else {
                memset(p, 0, sizeof *p);   /* recycled object: leave its new UI alone */
            }
            break;
        }
    }
    ReleaseSRWLockExclusive(&pickup_lock);
}

/* once a frame, from the head of f_831f3200: the wallet every 10 frames while the row is on. The game's registers are kept
   around the call: it runs inside the game's own frame */
void ocr_counters_frame(Ctx *c) {
    extern void f_80a87c30(Ctx *c);
    rx_option_set(OCR_OPT_PHOTO_READY, hos_oot_flight_shortcut_ready() && !hos_oot_story_event_active());
    static unsigned frames;
    static int sent = -2;
    if (!on() || !hos_oot_flight_shortcut_ready()) {
        if (sent != -1) rx_option_set(OCR_OPT_RUPEES, -1), sent = -1;
        frames = 0;
        return;
    }
    if (frames++ % 10) return;
    const uint64_t slot = recomp_load64(c, 0x84c9e0d0ull);   /* (the manager's pointer, as f_80a87e50 loads it at 0x80a88458) */
    const uint64_t mgr = slot ? recomp_load64(c, slot) : 0;
    int value = -1;
    if (mgr) {
        const Ctx keep = *c;
        c->x[0] = mgr;
        c->x[1] = 1;
        c->x[30] = 0;
        f_80a87c30(c);
        value = (int)(uint32_t)c->x[0];
        *c = keep;
        if (value < 0 || value > 9999) value = -1;   /* (not a wallet: nothing shown) */
    }
    if (value != sent) {
        rx_option_set(OCR_OPT_RUPEES, value), sent = value;
        static int said;
        if (said++ < 8) hos_log("[OcarinaReborn/COUNTERS] rupees: %d", value);
    }
}
