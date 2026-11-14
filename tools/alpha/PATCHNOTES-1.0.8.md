**Ocarina Reborn v1.0.8 — Patch Notes**

**📷 Photo mode**
- New free-camera photo mode with adjustable field of view and HUD-free PNG screenshots.
- Enable **F1 → Debug → Debug tools**. Press **F6** to toggle photo mode and **F7** to take a photo, or use the menu buttons.
- Photos are saved in the game's **Screenshots** folder. The world keeps running; photo mode is unavailable during dialogue and cutscenes.

**💎 Rupees in the Debug menu**
- Use **Add rupees** to add 1, 10, 50, 100 or 500 rupees, or choose **Fill wallet**.
- Your current wallet's capacity is respected.

**⚙️ Memory and stability**
- Reduced unused VRAM reservations with the default renderer settings, without lowering texture quality or resolution. The improvement depends on your GPU and the scene.
- Performance advice now recognizes sustained VRAM pressure when texture memory is set to **Auto**, and can suggest a smaller cache.
- Failed GPU submissions now stop with a specific error instead of potentially leaving the game waiting forever.
- Reading long session logs and exporting crash reports now uses less launcher memory.

**💬 Dialogue and visuals**
- Frame Generation temporarily pauses during conversations and cutscenes to help prevent text-box artifacts, then resumes automatically. During these scenes, displayed FPS reflect the actual game frame rate.
- Generated game executables now use the Ocarina icon.

**📊 Better Debug Packages**
- More detailed timelines for stutters, loading, CPU/GPU waits, RAM/VRAM pressure, file reads and scene changes, plus crash function names matched to the exact game build.
- Press **Ctrl+F8** when a problem happens, then close the game and create a fresh **Debug Package**. Please send it in **#post-your-logs-here** with the area, what happened and the approximate time.
- Added audio-state diagnostics to investigate battle music that keeps playing. This music issue is still under investigation; this update does not claim to fix it.
- Corrected misleading cache/virtual-driver advice and preserved more useful error details. A separate, optional 30-second Windows trace is available in **Diagnostic tools**.

**ℹ️ Updating**
- Restart the launcher and choose **Update**. Install over the existing version, then let the launcher update the game components.
- **No complete reinstall or game-file reimport is needed.** Saves, settings and local voice mods stay. Existing caches are kept; changed renderer components may still require shader preparation.

Thanks for testing and sharing your logs! 💙

[Ocarina Reborn](https://ocarina-pc-native-build.github.io/)
