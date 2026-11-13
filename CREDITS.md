# Source & credits

Ocarina Reborn builds on **[Hookshot](https://github.com/NotRexed/Hookshot), created by NotRexed and its contributors**. Hookshot provides the native recompilation engine, console runtime, Vulkan renderer and game-build pipeline. Credit for that foundation belongs to the Hookshot team and its upstream contributors.

The Ocarina Reborn v1.0.4 release uses **Hookshot v2.2.0-rc.1**, with Ocarina Reborn changes. Ocarina Reborn is independently maintained; it is not an official Hookshot release or an endorsement by the Hookshot team.

## Public source

| Component | Source |
| --- | --- |
| Original Hookshot project | [NotRexed/Hookshot](https://github.com/NotRexed/Hookshot) |
| Upstream version used in v1.0.4 | [Hookshot v2.2.0-rc.1](https://github.com/NotRexed/Hookshot/tree/v2.2.0-rc.1) |
| Ocarina Reborn's patched engine and renderer | [engine/](https://github.com/misterrageguy-cyber/OoT2026-PC-Recomp/tree/main/engine) |
| Hookshot game-build pipeline used by our launcher | [engine/nx2/](https://github.com/misterrageguy-cyber/OoT2026-PC-Recomp/tree/main/engine/nx2) |
| Hookshot Builder, retained in the upstream source tree | [engine/builder/](https://github.com/misterrageguy-cyber/OoT2026-PC-Recomp/tree/main/engine/builder) |
| Ocarina Reborn launcher | [tools/alpha/launcher/](https://github.com/misterrageguy-cyber/OoT2026-PC-Recomp/tree/main/tools/alpha/launcher) |
| Ocarina Reborn installer and build instructions | [BUILDING.md](https://github.com/misterrageguy-cyber/OoT2026-PC-Recomp/blob/main/BUILDING.md) |
| Exact released source snapshot and installer | [v1.0.4 release](https://github.com/misterrageguy-cyber/OoT2026-PC-Recomp/releases/tag/v1.0.4) |

The distributed Ocarina Reborn launcher is our Python/native Windows interface. It calls Hookshot's build tools through our preparation script. The upstream Hookshot Builder source is retained as part of the engine source tree; it is not the launcher interface shipped as Ocarina Reborn.

Ocarina Reborn's additions include launcher and installer integration, presets and performance diagnostics, settings/UI changes and custom gameplay hooks. The released engine tree already contains those changes; [SOURCE-MANIFEST.json](https://github.com/misterrageguy-cyber/OoT2026-PC-Recomp/blob/v1.0.4/SOURCE-MANIFEST.json) records its source hashes and matching installer. No claim is made that Ocarina Reborn created the underlying Hookshot engine.

## Licenses and acknowledgements

Hookshot is published under the **GNU General Public License, version 3 or later (GPL-3.0-or-later)**. Its license text is retained in [engine/LICENSE](https://github.com/misterrageguy-cyber/OoT2026-PC-Recomp/blob/main/engine/LICENSE), with an identical reference copy at [LICENSE-HOOKSHOT](LICENSE-HOOKSHOT). Existing copyright and license headers remain in the source. Changes made for Ocarina Reborn do not remove the upstream notices.

Hookshot includes work from other projects, including Eden, suyu, Sirit, SDL, Dear ImGui, zstd and zbic. See the [upstream credits](https://github.com/NotRexed/Hookshot/tree/v2.2.0-rc.1#credits) and the license files beside each dependency for their authors and terms. Where the view-distance parameters sit in game memory was identified by **hotoni's Graphics-Menu mod**, as credited in `engine/host/ocr_view.c`.

Third-party code, runtime components, media and trademarks retain their respective licenses and rights. The Hookshot license reference does not relicense those materials. NVIDIA DLSS has NVIDIA's separate license; AMD runtime license files are retained with those components.

This source does not contain the original Nintendo game source, a game dump, encryption keys or a built game executable. Building the game requires the user's own supported game file. Ocarina Reborn and Hookshot are unofficial community projects and are not affiliated with Nintendo.

The v1.0.4 renderer also integrates YakuzaFanA's [Hookshot light-table patch (PR #3047)](https://github.com/NotRexed/Hookshot/pull/3047), pinned to commit `9c75b3214262844b644c0a8cdbbe9b2bde590ace`.
