# Roadmap

Updated November 5, 2026 from [Development Update #01](UPDATE-01.md), reported local commit `e6125e6`. This roadmap does not promise a release date.

## Current milestone

- [x] Display game video, title screen, main menu and options menu.
- [x] Test opening and leaving the options menu.
- [x] Reach real 3D output, including the Deku Tree and dialogue.

**Real 3D output is visible, but heavy overexposure and a CPU return crash remain unresolved. Controllable gameplay and saving/loading are not yet verified.**

## 1. Resolve the current blockers

- [ ] Reproduce and fix the longer-run CPU return crash around frame **23,250**, reported at `main+0x1661690`.
- [ ] Identify and correct the cause of heavy overexposure, washed-out colours and missing visual detail.
- [ ] Prioritize relevant remaining shader errors from the **111** reported messages.
- [ ] Recheck the affected 3D scene and the menu/options path after fixes.

The current **0 Vulkan errors** result applies to the tested menu/options path; it does not establish error-free 3D rendering.

## 2. Reach controllable gameplay

- [ ] Reach the first genuinely controllable scene through the normal game flow.
- [ ] Verify player movement, camera behavior, collisions and interactions.
- [ ] Record the actual image output and the inputs tested.
- [ ] Confirm that progression continues beyond the current reproducible stop.

Visible scenes, dialogue or an increasing frame counter do not complete this milestone.

## 3. Save, restart, and continue

After controllable gameplay is reached:

- [ ] Run a continuous gameplay session.
- [ ] Check reachable room and scene transitions.
- [ ] Verify gameplay audio.
- [ ] Save through the game using a separate test profile.
- [ ] Close normally, restart, and load the saved progress.

Functions that cannot yet be reached remain unverified.

## 4. Improve stability and compatibility

- [ ] Test longer gameplay sections.
- [ ] Expand hardware coverage beyond the reported RX 7900 XTX test.
- [ ] Check startup and menu behavior for regressions.
- [ ] Report Vulkan validation results separately for menus and 3D scenes/gameplay.
- [ ] Measure performance before making targeted optimizations.

1440p and 60 FPS remain targets, not demonstrated performance figures.

[Back to the project overview](README.md)
