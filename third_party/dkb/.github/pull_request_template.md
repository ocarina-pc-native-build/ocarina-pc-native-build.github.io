## Problem

<!-- What is wrong or missing, and how it shows (log line, scene, issue number). -->

## Change

<!-- What this pull request changes, and why this way. One topic per pull request. -->

## How it was tested

<!-- Commit or base, GPU and driver, which scene, how long, fresh profile or not. -->

## Checklist

- [ ] `python tools/check_content.py --staged` passes, and nothing from the game is in this pull request (no game
      files, generated C, shaders, shader caches, builds or screenshots of the game).
- [ ] A change to the lifter (`recomp/`) or the CPU headers passes the differential tests ([docs/building.md](https://github.com/Lucas-blip-png/dkb-pc-recomp/blob/bananza/docs/building.md), "Checks").
- [ ] Copied code keeps its header and has a row in `THIRD_PARTY_NOTICES.md` with the upstream commit.
- [ ] Generated C is not edited by hand.
