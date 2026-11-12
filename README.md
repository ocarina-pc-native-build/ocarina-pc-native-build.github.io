# Ocarina Reborn

A native Windows x64 version of **The Legend of Zelda: Ocarina of Time (Switch 2)**, built on your PC from your own `.nup` game file.

**Current release: v1.0.0 · November 12, 2026**

[Download the latest release](https://github.com/ocarina-pc-native-build/ocarina-pc-native-build.github.io/releases/latest) · [Website](https://ocarina-pc-native-build.github.io/) · [Discord](https://discord.gg/vDPAcc6JnY)

## Get started

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

## What's new in v1.0.0

- **Performance reports:** actual game FPS, frame-time spikes, renderer CPU/GPU times and VRAM usage. Reports exclude menu samples and distinguish frame generation from game frames.
- **Revised presets:** CPU and RAM inform recommendations; the performance preset leaves frame generation off and supports lower output resolutions for integrated graphics.
- **Experimental texture saving:** Off / 1024 / 512 for selected large texture arrays. Off by default; restart the game after changing it. Performance gains on low-end hardware are not yet verified.
- **Reviewed adjustments:** the launcher explains suggested setting changes before applying them and backs up previous settings.

**After installing this update, rebuild the game once in the launcher.** To try texture saving, start with 1024 in Settings > Memory and restart the game. Switch back to Off and restart if you notice visual issues.

[Full release notes and SHA-256](https://github.com/ocarina-pc-native-build/ocarina-pc-native-build.github.io/releases/tag/v1.0.0) · [All releases](https://github.com/ocarina-pc-native-build/ocarina-pc-native-build.github.io/releases)

## Feedback and troubleshooting

For help or bug reports, join the [Discord](https://discord.gg/vDPAcc6JnY). Include your installed version, CPU/GPU, the steps that reproduce the issue and a fresh debug package created by the launcher. For controller-icon issues, also mention the controller model and whether you rebuilt the game after updating.

## Project and credits

Ocarina Reborn combines its own launcher, installer, settings and interface customizations with the [Hookshot v2.1.0 engine](https://github.com/NotRexed/Hookshot/tree/v2.1.0), licensed under GPL-3.0. The engine's copyright and license notices are retained in the distribution.

This repository hosts the public website, project information and installer releases. It does not contain the current launcher and engine build sources on `main`.

Ocarina Reborn is an unofficial community project and is not affiliated with Nintendo.

## Support

[Buy Me a Coffee](https://buymeacoffee.com/hotdevilsauce) — optional support for development tools, testing and ongoing work. Support does not purchase a game, early access or a guaranteed feature.

For website and release maintenance, see [PUBLISHING.md](PUBLISHING.md).
