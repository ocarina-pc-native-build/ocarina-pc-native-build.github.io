# Roadmap

This roadmap describes the next development milestones for Ocarina of Time — PC Native Build. It does not promise a release date. Progress is based on the supplied local development reports, most recently referencing `3555ea1` and `5971bd8`.

## 1. Reach controllable 3D gameplay

- [ ] Reproduce the working startup, title screen, main menu, and options menu path.
- [ ] Start a new game using a separate test profile without overwriting existing saves.
- [ ] Proceed through the normal introduction and loading sequence.
- [ ] Identify and fix the first reproducible blocker using logs and, where needed, stack traces.
- [ ] Prioritize the documented shader errors that affect the reached scene.
- [ ] Verify visible character and environment rendering, movement, camera behavior, collisions, and interactions.
- [ ] Record actual image output and the inputs tested.

A video, cutscene, or increasing frame counter does not complete this milestone.

## 2. Save, restart, and continue

After controllable gameplay is reached:

- [ ] Run a continuous gameplay session.
- [ ] Check reachable room and scene transitions.
- [ ] Verify gameplay audio.
- [ ] Save through the game when saving becomes available.
- [ ] Close normally, restart, and load the saved progress.

Functions that cannot yet be reached remain unverified.

## 3. Improve stability and compatibility

- [ ] Test longer gameplay sections.
- [ ] Expand hardware coverage beyond the reported RX 7900 XTX test.
- [ ] Check startup and menu behavior for regressions.
- [ ] Report Vulkan validation results separately for menus and gameplay.
- [ ] Measure performance before making targeted optimizations.

1440p and 60 FPS remain targets, not demonstrated performance figures.

[Back to the project overview](README.md)
