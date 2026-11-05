# Roadmap

Updated November 5, 2026 from the revised [Development Update #01](UPDATE-01.md), latest documented commit `e6125e6`. This roadmap does not promise a release date.

## Current milestone

- [x] Display game video, title screen, main menu and options menu.
- [x] Test opening and leaving the options menu.
- [x] Reach an actual 3D in-game scene, including the Deku Tree and dialogue.

**We’re now in-game!** Basic movement appears possible, but rendering problems need attention before gameplay can be properly assessed. Reliable gameplay, longer-run stability and saving/loading still need verification.

## 1. Fix the graphical issues

- [ ] Correct heavy overexposure and washed-out colours.
- [ ] Eliminate flickering.
- [ ] Fix the shader and rendering errors affecting the visible scene.
- [ ] Recheck lighting, colour output and visual detail after fixes.
- [ ] Check the menu/options path for regressions.

These issues are not fixed yet. The latest recorded **0 Vulkan errors** applies to the tested menu/options path; it does not establish error-free in-game rendering. The latest recorded shader report count is **111**, down from **464**.

## 2. Assess gameplay and longer-run stability

- [ ] Verify player movement, camera behavior, collisions and interactions once the scene can be properly assessed.
- [ ] Record the inputs tested and actual image output.
- [ ] Recheck the previously reported longer-run CPU crash and investigate it if it still occurs.
- [ ] Confirm that progression continues beyond the earlier stop around frame **23,250**, reported at `main+0x1661690`.
- [ ] Run a longer continuous gameplay session.

The earlier CPU crash has **not been confirmed resolved**. Initial movement observations do not establish reliable gameplay or longer-run stability.

## 3. Save, restart, and continue

- [ ] Check reachable room and scene transitions.
- [ ] Verify gameplay audio.
- [ ] Save through the game using a separate test profile.
- [ ] Close normally, restart, and load the saved progress.

Saving/loading remains unverified.

## 4. Improve compatibility and performance

- [ ] Expand hardware coverage beyond the reported RX 7900 XTX test.
- [ ] Check startup and menu behavior for regressions.
- [ ] Report Vulkan validation results separately for menus and in-game scenes.
- [ ] Measure performance before making targeted optimizations.

1440p and 60 FPS remain targets, not demonstrated performance figures.

[Back to the project overview](README.md)
