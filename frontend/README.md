# React views

React renders the Patients view: search, sample origin, disease chips, actions,
table, messages and pagination. Existing CSS and layout are unchanged.
Multimodal uses the same scope-bar and disease-chip components, with its current
modality selectors, combinations, patient list and inventory inspector.
React also renders the Clinical dashboard tables, chart cards and measurement
selector. Existing Plotly routines own only the graph interiors and sex legend;
plots are cleaned up when replaced or unmounted.
Timeline controls, availability rows and loading/retry states use React too.
Its controller retains time coordinates and plot traces. The patient inspector
and Multimodal share React sample, assay and clinical-record tables.
Workspace loading/reset explicitly unmounts both dashboard roots before showing
its notices.
Assay coverage and modality tabs, Imaging viewer status and the study table
also use React, along with detailed assay cards and the variant browser.
The shared chat list (folders, pins and selection), user/model administration
cards, dataset administration and bulk controls/confirmation dialogs, Jobs/Run history, saved cohorts,
the dataset picker/catalogue and analysis
catalogue/checklist use React too.
Query and Analysis conversations use React, including shared safe reply
formatting, result tables, actions, follow-ups and copy controls. Pheno-Ranker
uses React for conversation history, output tables, plot cards, alignment
details, explanations, planning reasoning and follow-ups. The custom-script
editor and analysis measurement selector also use React.
Dataset About dialogs and authentication/provider summaries use React.
Main preference fields and section navigation, chat move/clear-history forms,
and the keyboard-accessible chat-width divider also use React. Preference drafts
are separate from saved settings; the existing controllers handle persistence.
Storage paths, export limits, the About version report and deployment branding
also render with React. File validation and administrator checks stay in their
existing controllers and backend endpoints.
MCP sharing and approval panels, DICOM folder linking, molecular-export selection
and the project menu also use React. Tokens stay in controller memory only;
approval and export restrictions are still enforced by the backend.
Query, Analysis and Pheno-Ranker prompt panels, Analysis/Pheno-Ranker setup,
user/provider creation forms, the navigation rail, dashboard
tabs and account-menu contents mount through React before controllers capture
their controls. Prompt values remain native uncontrolled inputs so restored
drafts and existing execution handlers do not compete with React state.
Authentication and settings panel structures also mount through React before
their controllers bind. Progress cards and Query provenance badges use typed
React props, not generated HTML.
Analysis and Pheno-Ranker provenance also use typed badges. Analysis plot-card
markup remains behind an explicit escaped-HTML boundary, alongside sanitized
dataset Markdown and the existing trusted SVG icon catalogue. Outer page
scaffolding still uses templates. Navigation events and
permission updates retain their controllers.
Existing controllers retain
requests, persistence, permissions and execution logic.

The controller in `static/js/patient_overview.js` owns requests and Timeline
navigation. React renders the shared scope bar and clinical-filter editor;
the existing scope controller retains validation and request handling. Patients
and Multimodal use the same draft filters and explicit Apply action.

```bash
cd frontend
npm ci
npm run build
```

Edit `src/`, not `static/js/react/ui.js`. These views use one generated bundle.
The generated bundle
and licence files are committed so native, Desktop and Docker launches need no
additional Node runtime or frontend build. No CDN or browser-side dependencies.

The rest of the frontend is being migrated incrementally, preserving its layout
and backend APIs.
