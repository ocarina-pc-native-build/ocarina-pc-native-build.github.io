# Publishing and maintenance

Website: https://ocarina-pc-native-build.github.io/

Repository: https://github.com/ocarina-pc-native-build/ocarina-pc-native-build.github.io

The website is static HTML and CSS. It requires no build step, dependencies, analytics service, or API keys.

## GitHub Pages

1. Place this package in the root of `ocarina-pc-native-build/ocarina-pc-native-build.github.io`.
2. In the repository, open **Settings → Pages**.
3. Choose **Deploy from a branch**, select the branch containing these files and **/ (root)**, then save.
4. Use the published URL shown by GitHub after deployment succeeds.

Reference: [GitHub Pages publishing documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

Keep `index.html`, `README.md`, `ROADMAP.md`, `CHANGELOG.md`, and `.nojekyll` together so that local links resolve.

## Support link

The website and README link to [HotDevilSauce on Buy Me a Coffee](https://buymeacoffee.com/hotdevilsauce). If the profile URL changes, update both files together.

## Project media

- `project-artwork.png`: artwork supplied by the maintainer, displayed on the website and in the README.
- `development-video.mp4`: the original recording supplied by the maintainer, with player controls and no autoplay.

Keep both media files in the repository root. The website links directly to the MP4 as a playback fallback.

## Update project progress

Update the website and README together. Preserve the scope of each test, separate measured results from targets, and add new development milestones to the changelog. Only mark roadmap items complete after the corresponding functionality has been tested.
