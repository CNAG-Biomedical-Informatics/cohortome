# Frontend

React renders the application shell, dashboard views, conversations, analysis
results, administration, settings and dialogs. Existing CSS and layout are
preserved. Dataset Markdown uses a limited React renderer: raw HTML, embeds
and local-file links are not supported.

## Ownership

- React owns UI markup and stable chart hosts.
- React also owns navigation click handlers and account-menu state, positioning
  and dismissal. The navigation controller still applies workspace transitions
  and permission-aware active views; do not bind duplicate native click handlers.
- The rail owns the Projects menu and its keyboard/focus behaviour. The project
  controller handles file dialogs, downloads and workspace restoration.
- The chat sidebar owns New chat menu and search visibility/focus in React.
  Chat creation and search rendering delegate to the existing session controllers;
  the search input remains uncontrolled so chat creation can clear its draft.
- Plotly and Cytoscape own chart interiors, including their loading/error
  messages. The heatmap dendrogram remains a chart renderer.
- Controllers retain requests, permissions, persistence, execution and scope
  transitions. This is a view migration, not a rewrite of application state.
- Controller-driven forms use uncontrolled inputs where native handlers restore
  values or read changes. Do not add competing React state.
- Fixed SVG icons are the only React HTML-injection boundary. They come from the
  application catalogue, never dataset or model text.
- Shared workspace hosts use one root registry so notices, dashboard views and
  patient inspectors cannot leave competing roots behind. Other views retain
  their own dedicated hosts.

The server template only supplies the document envelope and escaped bootstrap
configuration. Dataset choices contain IDs and names, not registry paths.

## Source layout

- `page-shell.jsx` composes the screens in `shell/`; keep their DOM IDs stable.
- `analysis-setup/` holds scope, catalogue, composer and starter prompts.
- `../static/js/actions/` connects shell events to controllers by feature.
  Bind controls in JSX, not again in the startup script. Document-wide events
  such as dismissing an open ClarID popover remain native.
- `analysis-results/` holds result types and shared artifact presentations.
- `clinical-filters/` owns filter state, requests and cleanup; its view stays in
  `clinical-filters.jsx`.
- `cohorts/` separates actions, the library and dialogs.
- `shared/` contains small controls and the shared root lifecycle. Feature-specific
  renderers stay with their feature, not in a general-purpose helper collection.
- `../static/js/charts/` contains clinical, Analysis and Pheno-Ranker plot
  rendering. Controllers pass the existing state and selection callbacks;
  chart modules do not submit analyses or persist chats. Timeline retains its
  small, dedicated renderer in `timeline.js`.

`index.js` exports controller adapters. Split by responsibility, not by an
arbitrary line limit. Do not introduce a second owner for form or chart state.

## Build

```bash
cd frontend
npm ci
npm run format:check
npm run build
```

Edit `src/`, not `static/js/react/ui.js`. Commit the generated bundle and licence
files with source changes. Desktop, native and Docker launches need no Node
runtime or frontend build.

Run `npm run format` after editing components. Prettier is development-only and
is not included in installers or the browser bundle.

Run focused browser tests for the affected views. The rendering-boundary tests
guard against bringing HTML-string UI rendering back into controllers.
