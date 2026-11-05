# OoT2026 PC Native Build | Development Update #01

**November 5, 2026 · Latest reported local commit: `e6125e6`**

The project has reached an important milestone: **real 3D output is now visible, including the Deku Tree and dialogue.** This is still an experimental development build, not a playable release.

## Implemented and fixed

- Native game code successfully linked with the Windows runtime. All 58 previously unresolved PACGA cases implemented and tested.
- AV1 video decoding added. A reproduced thread-switch crash and shutdown hang fixed.
- Incorrect sRGB texture-view usage corrected, resolving the black screen in the tested startup path.
- Game video, the title screen, main menu and options menu now display correctly. Opening and leaving the options menu works.

## Latest testing

Testing was performed on an **AMD Radeon RX 7900 XTX**.

Shader error reports decreased from **203 to 111**, down from **464** in the earlier build. The tested menu/options path continues to report **0 Vulkan errors**.

**15 runtime checks, 17 project tests and 245 GPU checks passed.**

## Known issues

The 3D scene is still **heavily overexposed**, with washed-out colours and missing visual detail. The rendering issue is being investigated and is **not fixed yet**.

A longer test reproducibly stops around **frame 23,250**, at a CPU return reported as `main+0x1661690`.

**Controllable gameplay and saving/loading have not yet been verified.** Visible 3D scenes and working menus do not mean the full game is playable.

## Next priorities

Fix the CPU return crash, identify and correct the overexposure, resolve relevant remaining shader errors and reach the first genuinely controllable gameplay scene.

Thanks for following the development and supporting the project!

---

[Project overview](README.md) · [Roadmap](ROADMAP.md) · [Website](https://ocarina-pc-native-build.github.io/) · [Discord](https://discord.gg/vDPAcc6JnY) · [Buy Me a Coffee](https://buymeacoffee.com/hotdevilsauce)

*This update records the maintainer’s local development report. The commit identifier refers to local game development; this website repository does not include that code history.*
