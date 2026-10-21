# Documentation

The site uses Docusaurus. From this directory, with Node.js 22:

```bash
npm ci
npm start
```

For a production build and local preview:

```bash
npm run build
npm run serve
```

## Manual publication

Pages will be enabled after the repository becomes public. No site is published
by adding or pushing the workflow.

Once public:

1. In repository **Settings → Pages**, select **GitHub Actions** as the source.
2. Open **Actions → Publish documentation → Run workflow** and choose `main`.
3. Follow the deployment link when the workflow finishes.

The site URL will be
<https://cnag-biomedical-informatics.github.io/cohortome/>.

The workflow only runs on manual dispatch, and skips publication for private
repositories or branches other than `main`. It builds from committed files with
`npm ci` and uploads only `docs-site/build/`. It does not build the application,
prepare datasets, or require a personal access token. Pages permissions are
limited to the deployment job. No `gh-pages` branch is needed.

Local, untracked documents can appear in a local Docusaurus build even when they
are absent from the sidebar. Do not upload local build output containing working
notes. The workflow checks out committed source instead.
