# Publishing Ocarina Reborn

The launcher checks `https://api.github.com/repos/ocarina-pc-native-build/ocarina-pc-native-build.github.io/releases/latest`. Preserve that repository and the exact asset name `Ocarina-Reborn-Alpha-Setup.exe` so existing installations can update.

1. Increase the numeric version in `tools/alpha/VERSION` (v1.0.6 follows v1.0.5); keep build-info and installer resources consistent.
2. Build a fresh installer from the cleaned source. Both staging recipes must pass the distribution guard. Keep the installer AppId and per-user installation path unchanged.
3. Run the project tests, native build/smoke checks and upgrade checks. Verify no game files, private keys, bundled recordings or unverified project media enter the source archive or installer.
4. Publish the corresponding launcher/engine/build source and source archive. Tag that source commit in both the source repository and the website repository (source/vX.Y.Z branch); the release tag must identify actual project source, not only website files.
5. Create draft releases in BOTH repositories. Upload the installer, its SHA-256 text file, the source ZIP and its SHA-256 file. Verify uploaded sizes and SHA-256 digests.
6. Keep exactly one 64-character lowercase checksum in the release body: the installer's SHA-256. Old launchers read the first such value. Source hashes belong in the separate checksum file.
7. Publish as a stable, non-prerelease release and mark it latest. Update the website and confirm the previous launcher offers the new version and verifies the same installer checksum.

The source repository is `misterrageguy-cyber/OoT2026-PC-Recomp`. The update/website repository is `ocarina-pc-native-build/ocarina-pc-native-build.github.io`. Never push to unrelated remotes.

Older releases withdrawn during the media cleanup remain withdrawn. Do not republish old installers, restore old assets or merge history from pre-cleanup clones. User game files, saves, settings and local imports stay outside the installer and public source.

## Website appearance

On November 14, 2026, the project owner requested restoration of the former website appearance while keeping v1.0.6 current. Only the former HTML/CSS presentation and its five referenced website images were restored, as new files on the cleaned history. This did not restore old installers, bundled recordings, launcher artwork, or old Git branches/tags. It is not a new statement about rights to those website images. Keep installer-media provenance checks in place.
