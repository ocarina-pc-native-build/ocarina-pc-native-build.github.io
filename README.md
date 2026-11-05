# Ocarina of Time — PC Native Build

![Ocarina of Time Native 2026 project artwork](project-artwork.png)

### Native Windows x64 recompilation · Switch 2 → PC

**Experimental build · Real 3D output visible · Controllable gameplay unverified**

I’m working on a native Windows x64 recompilation of the Switch 2 version of **Ocarina of Time**. The goal is to run the translated game code with a Windows runtime and a Vulkan graphics backend.

This project page documents my current development progress and the next steps. **There is no playable release yet.**

**Project website:** [ocarina-pc-native-build.github.io](https://ocarina-pc-native-build.github.io/)  
**Discord:** [Join our Discord](https://discord.gg/vDPAcc6JnY)  
**Maintainer:**  https://github.com/HotDevilSauce
**Status updated:** November 5, 2026  
**Latest reported local development commit:** `e6125e6`  
**Latest report:** [Development Update #01](UPDATE-01.md)

## Development Update #01 — first real 3D output

**November 5, 2026 · Reported local commit: `e6125e6`**

**Real 3D output is now visible, including the Deku Tree and dialogue.** This is an experimental development milestone. **There is no playable release yet, and controllable gameplay and saving/loading have not been verified.**

### Implemented and fixed

- Native game code linked successfully with the Windows runtime; all **58** previously unresolved PACGA cases implemented and tested.
- **AV1 video decoding** added; a reproduced thread-switch crash and shutdown hang fixed.
- Incorrect **sRGB texture-view usage** corrected, resolving the black screen in the tested startup path.
- Game video, title screen, main menu and options menu display correctly. Opening and leaving the options menu works.
- The Deku Tree and dialogue are now visible in real 3D output, with rendering problems still present.

### Latest testing

Reported testing used an **AMD Radeon RX 7900 XTX**.

| Metric | Earlier report | Previous report | Update #01 |
| :--- | ---: | ---: | ---: |
| Shader error reports | 464 | 203 | **111** |
| Vulkan errors in the tested menu/options path | 2 | 0 | **0** |

| Passed checks | Reported count |
| :--- | ---: |
| Runtime checks | **15** |
| Project tests | **17** |
| GPU checks | **245** |

The zero Vulkan error count applies to the tested menu/options path. Shader report counts do not necessarily represent distinct shaders or root causes.

### Known issues

- **Heavy overexposure:** washed-out colours and missing visual detail in the 3D scene. The rendering issue is being investigated and **is not fixed yet**.
- **Reproducible CPU return crash:** a longer test stops around **frame 23,250**, at a CPU return reported as `main+0x1661690`.
- **Controllable gameplay and saving/loading remain unverified.** Visible 3D scenes and working menus do not establish full playability, stable gameplay performance, or compatibility with other hardware.

### Next priorities

1. Fix the CPU return crash.
2. Identify and correct the overexposure.
3. Resolve relevant remaining shader errors.
4. Reach and verify the first genuinely controllable gameplay scene.
5. Then test scene transitions, saving/loading, longer sessions and additional hardware.

[Read the full Development Update #01](UPDATE-01.md) · [Detailed roadmap](ROADMAP.md) · [Earlier milestones](CHANGELOG.md)

## Earlier development video

[Watch the development video on the project website](https://ocarina-pc-native-build.github.io/#video) · [Open the MP4 recording](https://ocarina-pc-native-build.github.io/development-video.mp4) (14.7 MB)

Earlier startup/menu footage recorded November 5, 2026. This video does not show the new 3D milestone in Update #01. The banner above is project artwork.

## Join the community

[Join our Discord](https://discord.gg/vDPAcc6JnY) to discuss development progress, share feedback, and connect with other project followers.

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

*All progress claims refer to local development reports. Visible 3D scenes and tested menu features are explicitly distinguished from controllable gameplay that has not yet been verified.*
