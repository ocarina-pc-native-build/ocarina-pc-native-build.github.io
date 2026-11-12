# Ocarina Reborn

A native Windows x64 version of **The Legend of Zelda: Ocarina of Time (Switch 2)**, built on your PC from your own `.nup` game file.

**Current release: v1.0.1 · November 12, 2026**

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

## What's new in v1.0.1 — Big Update

- **Fixes:** Xbox, PlayStation and Steam Deck button icons are generated again; all 16 game languages can be selected (incl. Português (Brasil)); the launcher's enemy damage applies with the debug tools on; out-of-memory crashes are softened (the game waits for Windows to grow the page file, and the launcher explains the fix).
- **Lower-end PCs (Settings > Memory):** RAM guard (on by default), largest-texture limit (1024 for 4-6 GB cards), low-spec mode and compact video memory (test).
- **Reborn Auto:** measure a short route, review a suggestion, then compare a second run. **Prepare shaders** rebuilds the shader cache without rebuilding the game.
- **Reborn look:** six colour grades in F1 > Graphics or the launcher (not with HDR).
- **Gameplay:** One-hit mode (Settings > Difficulty) and a Speedrun timer (F1 > Gameplay).
- **Mods:** a Mods page in the launcher to turn RomFS mods on and off and add them from a ZIP or folder.

**The launcher rebuilds the game once after installing this update** (about 5 minutes on our test PC). The low-end options still need testing on weaker hardware; no FPS gains are promised.

[Full release notes and SHA-256](https://github.com/ocarina-pc-native-build/ocarina-pc-native-build.github.io/releases/tag/v1.0.1) · [All releases](https://github.com/ocarina-pc-native-build/ocarina-pc-native-build.github.io/releases)

## Feedback and troubleshooting

For help or bug reports, join the [Discord](https://discord.gg/vDPAcc6JnY). Include your installed version, CPU/GPU, the steps that reproduce the issue and a fresh debug package created by the launcher. For controller-icon issues, also mention the controller model and whether you rebuilt the game after updating.

## Project and credits

Ocarina Reborn combines its own launcher, installer, settings and interface customizations with the [Hookshot v2.1.0 engine](https://github.com/NotRexed/Hookshot/tree/v2.1.0), licensed under GPL-3.0. The engine's copyright and license notices are retained in the distribution.

This repository hosts the public website, project information and installer releases. It does not contain the current launcher and engine build sources on `main`.

Ocarina Reborn is an unofficial community project and is not affiliated with Nintendo.

## Support

[Buy Me a Coffee](https://buymeacoffee.com/hotdevilsauce) — optional support for development tools, testing and ongoing work. Support does not purchase a game, early access or a guaranteed feature.

For website and release maintenance, see [PUBLISHING.md](PUBLISHING.md).
