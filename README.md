# Ocarina Reborn

This repository contains the **Ocarina Reborn launcher, patched engine and build scripts**, and hosts installer releases for RecompStore. The website is [ocarina-pc-native-build.github.io](https://ocarina-pc-native-build.github.io/).

A native Windows x64 version of **The Legend of Zelda: Ocarina of Time (Switch 2)**, built on your PC from your own `.nup` game file.

**Current release: v1.0.8 · November 14, 2026**

[Download the latest release](https://github.com/ocarina-pc-native-build/ocarina-pc-native-build.github.io/releases/latest) · [Website](https://ocarina-pc-native-build.github.io/) · [Discord](https://discord.gg/vDPAcc6JnY)

## Source code

The actual **v1.0.8 source** is here: [engine and renderer](engine/), [game-build pipeline](engine/nx2/), [Ocarina Reborn launcher](tools/alpha/launcher/), [installer/build scripts](scripts/), [custom hooks and graphics](tools/alpha/hud/), [tests](tools/alpha/tests/) and [build instructions](BUILDING.md). The original [engine builder source](engine/builder/) is retained alongside the Ocarina Reborn launcher.

`engine/` contains the already-patched sources used by the released installer, including custom tunic colors and the classic counters fix. Classic-voice preparation imports a user-selected ZIP; recordings are not bundled. `SOURCE-MANIFEST.json` records the engine file hashes and the matching installer SHA-256. GitHub's v1.0.8 source archives contain this project source; the website lives in its separate repository.

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

## What's new in v1.0.8

- **Photo mode:** free camera, adjustable field of view and HUD-free PNG screenshots. Enable Debug tools in F1 → Debug; F6 toggles photo mode and F7 takes a photo. The world keeps running.
- **Add rupees:** choose an amount or fill the current wallet from the Debug menu.
- **Memory and stability:** smaller default VRAM allocation blocks, improved Auto-cache advice, explicit GPU submission failures and bounded log reading.
- **Dialogue protection:** Frame Generation pauses during conversations/cutscenes and resumes automatically afterwards.
- **Diagnostics:** detailed stutter/loading timelines, matching crash function names and Ctrl+F8 problem markers. Audio-state logging supports the continuing battle-music investigation.
- **Game icon:** generated executables use the Ocarina icon.

Update over the existing installation and let the launcher update the game components. No complete reinstall or game-file reimport is required. Saves, settings and local voice mods stay. Existing caches are kept; renderer changes may still require shader preparation.

[Full release notes and SHA-256](https://github.com/ocarina-pc-native-build/ocarina-pc-native-build.github.io/releases/tag/v1.0.8) · [All releases](https://github.com/ocarina-pc-native-build/ocarina-pc-native-build.github.io/releases)

## Feedback and troubleshooting

For help or bug reports, join the [Discord](https://discord.gg/vDPAcc6JnY). Include your installed version, CPU/GPU, the steps that reproduce the issue and a fresh debug package created by the launcher. For controller-icon issues, also mention the controller model and whether you rebuilt the game after updating.

## Licenses

The engine is distributed under [GPL-3.0-or-later](engine/LICENSE). Existing copyright and third-party license notices remain with the code. See [license notices and corresponding source](CREDITS.md) for component terms and release sources.

This repository hosts the project source, build instructions and installer releases. Its Pages entry redirects to the main project website.

Ocarina Reborn is an unofficial community project and is not affiliated with Nintendo.

## Support

[Buy Me a Coffee](https://buymeacoffee.com/hotdevilsauce) — optional support for development tools, testing and ongoing work. Support does not purchase a game, early access or a guaranteed feature.

For release maintenance, see the [main repository publishing notes](https://github.com/ocarina-pc-native-build/ocarina-pc-native-build.github.io/blob/main/PUBLISHING.md).