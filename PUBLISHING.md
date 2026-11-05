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

## Add Buy Me a Coffee later

Once the account exists, verify its exact profile URL before adding it.

- In `index.html`, replace the pending support label with an anchor pointing to that profile, and remove the “Coming soon” and unavailable-page text.
- In `README.md`, replace the “coming soon” line with a link to the verified profile.
- Optionally create `.github/FUNDING.yml` containing `buy_me_a_coffee: YOUR_VERIFIED_USERNAME` after replacing the example with the actual username. Do not publish the example value.

The present website intentionally has no active payment link.

## Update project progress

Update the website and README together. Preserve the scope of each test, separate measured results from targets, and add new development milestones to the changelog. Only mark roadmap items complete after the corresponding functionality has been tested.
