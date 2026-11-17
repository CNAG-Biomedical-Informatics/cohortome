# Cohort-building React views

React renders the Patients view: search, sample origin, disease chips, actions,
table, messages and pagination. Existing CSS and layout are unchanged.
Multimodal uses the same scope-bar and disease-chip components, with its current
modality selectors, combinations, patient list and inventory inspector.

The controller in `static/js/patient_overview.js` owns requests and Timeline
navigation. The shared scope bar and clinical-filter editor are mounted in
dedicated hosts with cleanup; React does not modify their children. Patients
and Multimodal still use the same filter rules and explicit Apply action.

```bash
cd frontend
npm ci
npm run build
```

Edit `src/`, not `static/js/react/ui.js`. Both views use one generated bundle.
The generated bundle
and licence files are committed so native, Desktop and Docker launches need no
additional Node runtime or frontend build. No CDN or browser-side dependencies.

This is a contained experiment, not a migration of the rest of the application.
