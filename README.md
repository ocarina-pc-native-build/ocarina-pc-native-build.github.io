# Ocarina of Time — PC Native Build

![Ocarina of Time Native 2026 project artwork](project-artwork.png)

### Native Windows x64 recompilation · Switch 2 → PC

**In development · Video and menus working · 3D gameplay not yet verified**

I’m working on a native Windows x64 recompilation of the Switch 2 version of **Ocarina of Time**. The goal is to run the translated game code with a Windows runtime and a Vulkan graphics backend.

This project page documents my current development progress and the next steps. **There is no playable release yet.**

**Project website:** [ocarina-pc-native-build.github.io](https://ocarina-pc-native-build.github.io/)  
**Maintainer:**  https://github.com/HotDevilSauce
**Status updated:** November 5, 2026  
**Latest reported local development commits:** `3555ea1` and `5971bd8`

## Development video

[Watch the development video on the project website](https://ocarina-pc-native-build.github.io/#video) · [Open the MP4 recording](https://ocarina-pc-native-build.github.io/development-video.mp4) (14.7 MB)

Recorded November 5, 2026. The artwork above is project artwork; the video is the development recording. See the status below for the scope of reported testing.

## Current milestone

The black screen in the tested startup path has been fixed. **Actual game video, the title screen, and the main menu are displayed.** An input test successfully opens the options menu and returns.

The cause was an incorrectly used write view for an sRGB texture. According to the local development report, the fix was tested on an **AMD Radeon RX 7900 XTX**.

| Metric in the tested startup and menu path | Before | Latest report |
| :--- | ---: | ---: |
| Vulkan errors | 2 | **0** |
| Shader error messages | 464 | **203** |

The latest reported run included **3,000 Vulkan presentations** and ended normally. This count does not demonstrate playable 3D gameplay or a particular frame rate.

**Tests:** 13 runtime checks, 17 existing tests, and additional regression tests were reported as passing. The exact number of additional regression tests was not specified.

## What is working so far

| Area | Status according to the local development report |
| :--- | :--- |
| Windows test runtime | Debug and Release builds created |
| Translated game code | 551 generated C files compiled natively |
| PACGA | All 58 previously outstanding sites implemented and checked |
| Linking | Zelda code linked with the Windows runtime |
| Video playback | AV1 decoding added; actual game video visible |
| Startup and menus | Title screen and main menu visible |
| Input | Options menu opened and return path tested successfully |
| Stability | Reproduced thread-switch crash and shutdown hang fixed |
| Vulkan validation | No errors in the most recently tested startup and menu path |

## What remains unresolved

**3D gameplay and full playability have not yet been verified.** Full runtime integration is also still in progress. A working main menu is an important milestone, but it does not demonstrate that the entire game works.

There are **203 documented shader error messages** remaining. This is a message count, not necessarily 203 distinct shaders or root causes. Additional scenes may reveal further issues.

A controllable 3D scene, working scene transitions, in-game saving and loading, and a stable frame rate over longer gameplay sessions have not yet been demonstrated. Compatibility with other graphics cards or systems is not promised.

## Next steps

- [ ] Reach the first controllable 3D scene through “New Game.”
- [ ] Fix shader and runtime issues that affect gameplay.
- [ ] Test movement, camera behavior, collisions, and interactions.
- [ ] Check scene transitions, saving, restarting, and loading.
- [ ] Then investigate stability, additional hardware, and performance.

See the [roadmap](ROADMAP.md) for details and the [changelog](CHANGELOG.md) for reported milestones.

## Support the project

I’m developing this project independently. Voluntary support helps cover **development tools, testing, and ongoing development work**, including investigating bugs and documenting progress.

**[Buy Me a Coffee](https://buymeacoffee.com/hotdevilsauce)** — support independent development.

Support is optional and does not purchase a game, early access, or a guaranteed release. Following the project and sharing useful feedback also help.

## Development platform

The target platform is **Windows x64 with Vulkan**. The reported graphics test was performed on a **Radeon RX 7900 XTX**. The intended development PC uses a Ryzen 7 9800X3D and 32 GB RAM.

These details describe the development machine, **not minimum system requirements**. 1440p and 60 FPS are targets, not achieved or guaranteed performance figures.

## Release

This package contains only the project description and status website. It contains **no ROMs, Nintendo keys, extracted game assets, generated game code, or game binaries**. No download sources for these are provided here.

A public source-code release, installer, and release date have not been announced. The local commit identifiers document the reported development state; this status site does not automatically include the associated code history.

This is an unofficial project and is not affiliated with Nintendo.

---

*All progress claims refer to local development reports. Tested startup and menu features are explicitly distinguished from gameplay that has not yet been verified.*
