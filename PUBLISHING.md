> Public downloads are paused after the distribution review. Old release links and checksums below are historical; do not re-upload previous installers or media. Use the current main source and its distribution guard.

# Website and release maintenance

Website: <https://ocarina-pc-native-build.github.io/>

Repository: <https://github.com/ocarina-pc-native-build/ocarina-pc-native-build.github.io>

## Repository contents

The `main` branch contains the static GitHub Pages website and current project information:

- `index.html`: website markup, styles and JavaScript.
- `assets/`: images used by the website.
- `.nojekyll`: keeps the site served as static files.
- `README.md`: current release, installation steps, features and support links.
- `PUBLISHING.md`: maintenance notes.

There is no build step for the website. Preserve the existing GitHub Pages configuration. Website edits are published from `main`.

## Updating project information

Keep the current version in the README consistent with the hero badge and latest-update section in `index.html`. Use the published release notes as the source for release changes. Link to GitHub Releases for the full release history and checksums.

Before removing an asset, check all HTML, CSS, JavaScript and Markdown references, including `srcset` and CSS `url()` values. Keep the favicon and responsive image variants used by the website. Check relative links and fragment targets after edits.

## Installer releases

The launcher checks this repository's `releases/latest` endpoint. The website also links to these releases.

- Keep the installer asset named **`Ocarina-Reborn-Alpha-Setup.exe`** so existing download and update clients continue to work.
- Use a new three-part version for each installer release, a tag such as `v0.0.10` and a title such as `Ocarina Reborn v0.0.10`.
- Include the uploaded installer's **SHA-256** in the release notes; the launcher uses it to verify the download.
- Publish the installer release as the latest release, without the prerelease flag.
- Mirror the same installer and notes to [misterrageguy-cyber/OoT2026-PC-Recomp](https://github.com/misterrageguy-cyber/OoT2026-PC-Recomp/releases), which supplies the RecompStore listing.

Website or documentation cleanup does not require a new installer version. Keep existing releases, tags and download URLs intact when maintaining the site.

## Community links

- Discord: <https://discord.gg/vDPAcc6JnY>
- Optional support: <https://buymeacoffee.com/hotdevilsauce>

Update the website and README together if these links change. Do not add game files, Nintendo keys, private signing material or generated game binaries to this repository.
