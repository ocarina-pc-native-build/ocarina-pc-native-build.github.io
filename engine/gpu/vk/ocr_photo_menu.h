/* Transient photo state. No saved graphics setting or shader-cache key changes. */
#pragma once
#include <atomic>
#include <filesystem>
#include <chrono>
#include <ctime>
#include "../../host/ocr_tools.h"

namespace mkwvk { int photo_ask_next(const char*, void (*)(void*, int64_t, int), void*); }
namespace mkwvk::photo_tools {
inline std::atomic<bool> active{false};
inline std::atomic<int64_t> ready_at{0};
inline std::atomic<int> lens{100}, shot_status{0};
inline int capture_frames = 0; // presenting thread only
inline bool ready() {
    const int64_t at = ready_at.load();
    return at && prof_now() - at < 300000000LL;
}
inline void availability(int available) {
    ready_at.store(available ? prof_now() : 0);
    if (!available) active.store(false);
}
inline void toggle(bool enabled, int current_fov) {
    if (!enabled) active.store(false);
    else if (ready() && !active.exchange(true)) lens.store(current_fov);
}
inline void request_capture() {
    if (!active.load() || shot_status.load() == 1 || shot_status.load() == 2) return;
    // Let the game apply the HUD mask and close the menu before requesting a present.
    capture_frames = 3;
    shot_status.store(1);
}
inline void tick(bool tools_enabled) {
    if (!tools_enabled || !ready()) active.store(false);
    if (!capture_frames) return;
    if (!active.load()) { capture_frames = 0; shot_status.store(-1); return; }
    if (--capture_frames) return;
    char module[MAX_PATH];
    const DWORD n = game_module_path(module, MAX_PATH);
    if (!n || n >= MAX_PATH) { shot_status.store(-1); return; }
    const auto folder = std::filesystem::path(module).parent_path() / "Screenshots";
    std::error_code ec;
    std::filesystem::create_directories(folder, ec);
    if (ec) { shot_status.store(-1); logf("photo: cannot create Screenshots (%s)", ec.message().c_str()); return; }
    const auto stamp = std::chrono::system_clock::now();
    const std::time_t seconds = std::chrono::system_clock::to_time_t(stamp);
    std::tm now{};
#ifdef _WIN32
    if (localtime_s(&now, &seconds)) { shot_status.store(-1); return; }
#else
    if (!localtime_r(&seconds, &now)) { shot_status.store(-1); return; }
#endif
    const int millis = (int)(std::chrono::duration_cast<std::chrono::milliseconds>(stamp.time_since_epoch()).count() % 1000);
    static unsigned sequence = 0;
    char name[128];
    snprintf(name, sizeof name, "OcarinaReborn-%04d%02d%02d-%02d%02d%02d-%03d-%lu-%u.png",
             now.tm_year + 1900, now.tm_mon + 1, now.tm_mday, now.tm_hour, now.tm_min, now.tm_sec, millis,
             GetCurrentProcessId(), ++sequence);
    const std::string path = (folder / name).string();
    shot_status.store(2);
    if (!photo_ask_next(path.c_str(), [](void*, int64_t, int ok) {
            shot_status.store(ok ? 3 : -1);
            logf("photo: PNG %s", ok ? "saved in Screenshots" : "capture failed");
        }, nullptr)) shot_status.store(-1);
}
inline const char* capture_text() {
    switch (shot_status.load()) {
    case 1: return "Queued";
    case 2: return "Saving...";
    case 3: return "Saved";
    case -1: return "Failed - retry";
    default: return "";
    }
}
} // namespace mkwvk::photo_tools
