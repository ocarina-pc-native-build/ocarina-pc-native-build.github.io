# Ocarina Reborn

The project website: **https://ocarina-pc-native-build.github.io/**

**Current release: v1.1.5 · November 22, 2026**

[Download / Releases](https://github.com/ocarina-pc-native-build/ocarina-pc-native-build.github.io/releases/latest) · [Discord](https://discord.gg/vDPAcc6JnY)

The website includes the forest background, feature cards, update section and community links. The current launcher and downloadable installer are v1.1.5: memory and responsiveness improvements, ocarina selection and optional unlimited amiibo scans.

## Updating

Restart the launcher and click **Update**, then install over your existing installation. Afterwards, let the launcher update the game components. Saves and settings stay; existing working game data is reused.

## Latest update

- Better graphics-buffer reuse, background cleanup and memory-pressure handling.
- Intended compiler optimizations for frequently used game code are now included in player builds.
- Improved texture-upload scheduling and controller-driver polling.
- Choose either ocarina for child or adult Link in Launcher Settings or F1 → Gameplay.
- Optional unlimited amiibo scans, off by default; location and story requirements remain.
- Recovery from corrupted build metadata and protection against accidental private profiling.
- More detailed memory and stutter diagnostics.

Restart the launcher and use **Update**, then let it update the game once. The first start may prepare shaders; keep working caches. No uninstall or game-file reimport is needed. Saves and settings stay. Performance varies by PC and area; some stutters remain.

[Full release notes and SHA-256](https://github.com/ocarina-pc-native-build/ocarina-pc-native-build.github.io/releases/tag/v1.1.5)

## Licenses

The engine is distributed under [GPL-3.0-or-later](LICENSE). [License notices and corresponding source](CREDITS.md) are provided with the releases.

This repository's main branch contains the website. The actual launcher, engine and build source is in [OoT2026-PC-Recomp](https://github.com/misterrageguy-cyber/OoT2026-PC-Recomp), also linked from each release. Existing launchers use this repository's latest stable release and the `Ocarina-Reborn-Alpha-Setup.exe` asset name.

[Optional project support](https://buymeacoffee.com/hotdevilsauce) · [Publishing procedure](PUBLISHING.md)

Ocarina Reborn is an unofficial community project, not affiliated with Nintendo. No game files or encryption keys are provided.
