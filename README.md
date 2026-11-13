# Ocarina Reborn

**Built on [Hookshot](https://github.com/NotRexed/Hookshot) by NotRexed and its contributors.** Hookshot provides the recompilation engine, Vulkan renderer and game-build pipeline. Ocarina Reborn adds its own launcher, installer and project-specific changes. [Source & credits](CREDITS.md) · [Hookshot license](LICENSE-HOOKSHOT)

A native Windows x64 version of **The Legend of Zelda: Ocarina of Time (Switch 2)**, built on your PC from your own `.nup` game file.

**Current release: v1.0.3 · November 13, 2026**

[Download the latest release](https://github.com/ocarina-pc-native-build/ocarina-pc-native-build.github.io/releases/latest) · [Website](https://ocarina-pc-native-build.github.io/) · [Discord](https://discord.gg/vDPAcc6JnY)

## Get started

The **engine, builder tools and launcher source** are public: [Ocarina Reborn source repository](https://github.com/misterrageguy-cyber/OoT2026-PC-Recomp), [build instructions](https://github.com/misterrageguy-cyber/OoT2026-PC-Recomp/blob/main/BUILDING.md) and [v1.0.3 source on this repository](https://github.com/ocarina-pc-native-build/ocarina-pc-native-build.github.io/tree/source/v1.0.3). This repository's `main` branch hosts the website.

1. Download `Ocarina-Reborn-Alpha-Setup.exe` from the latest release and install it.
2. Open Ocarina Reborn and read the development-build notice.
3. Select your own supported `.nup` game file in the launcher and build the game.
4. Connect and turn on your controller before starting the game, then launch it from the launcher.

You need Windows x64, a Vulkan-capable graphics card and your own supported game file. The installer does not include the game, ROMs or Nintendo keys. This is an early development release; compatibility, performance and stability vary by hardware and game area.

## Included features

- **Native rendering:** Vulkan graphics, resolution and display settings, widescreen and ultrawide support.
- **Controller support:** Xbox, PlayStation and Switch controllers, with matching button prompts.
- **Graphics options:** AMD FSR 3.1, FSR 4 on supported AMD hardware, and optional NVIDIA DLSS/DLAA through the launcher's separate setup.
- **Launcher tools:** local game building, update checks, save management and settings.
- **Performance tools:** quality, balanced and performance presets, FPS display and diagnostics.
- **Gameplay options:** difficulty and enemy-damage adjustments, cheat tools and control settings.

NVIDIA's DLSS files are downloaded separately through the launcher after accepting NVIDIA's license.

## What's new in v1.0.3

- **Included classic Link voices:** in Settings > Audio, choose Default or Classic (N64) independently for Young and Adult Link, then save and restart. Preparation is automatic; no separate voice download or import is needed. Dedicated cutscene voices remain unchanged.
- **Classic counters (N64):** a bottom-left rupee counter after loading a save, with pickup counters above Link hidden.
- **Graphics:** FXAA, view distance, grass density and shadow distance.
- **Engine v2.2.0-rc.1:** expanded FPS/frame-time displays, camera and control options, V-Sync Auto/On/Off, FSR 4 with native HDR and multiple engine fixes.
- **Stability:** stronger physical-RAM/VRAM protection, an automatic texture-memory limit of 40% of RAM and Compute mesh shaders on AMD RX 6000 cards.
- **Fixes:** fairy revivals no longer increase the death counter; localized startup text, corrected presets and accessible settings categories.

**Updating from 1.0.2 rebuilds the game once for the new engine**, with updated shaders prepared on first launch. Saves and settings stay. Selecting a classic voice only prepares its audio files and does not rebuild the engine or shaders.

[Full release notes and SHA-256](https://github.com/ocarina-pc-native-build/ocarina-pc-native-build.github.io/releases/tag/v1.0.3) · [All releases](https://github.com/ocarina-pc-native-build/ocarina-pc-native-build.github.io/releases)

## Feedback and troubleshooting

For help or bug reports, join the [Discord](https://discord.gg/vDPAcc6JnY). Include your installed version, CPU/GPU, the steps that reproduce the issue and a fresh debug package created by the launcher. For controller-icon issues, also mention the controller model and whether you rebuilt the game after updating.

## Project and credits

The released engine is based on [Hookshot v2.2.0-rc.1](https://github.com/NotRexed/Hookshot/tree/v2.2.0-rc.1), by **NotRexed and the Hookshot contributors**, under **GPL-3.0-or-later**. The original copyright, license and third-party notices are retained. Our changes are published alongside the engine. Ocarina Reborn is independently maintained and is not an official Hookshot release.

See [Source & credits](CREDITS.md) for direct links to the engine, Hookshot build pipeline, retained upstream Builder source and Ocarina Reborn launcher. Thanks to the Hookshot team and the projects it builds on for making this work possible.

Ocarina Reborn is an unofficial community project and is not affiliated with Nintendo.

## Support

[Buy Me a Coffee](https://buymeacoffee.com/hotdevilsauce) — optional support for development tools, testing and ongoing work. Support does not purchase a game, early access or a guaranteed feature.

For website and release maintenance, see [PUBLISHING.md](PUBLISHING.md).
