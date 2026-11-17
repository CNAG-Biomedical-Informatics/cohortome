# Patients React experiment

React renders the Patients view: search, sample origin, disease chips, actions,
table, messages and pagination. Existing CSS and layout are unchanged.

The controller in `static/js/patient_overview.js` owns requests and Timeline
navigation. The shared scope bar and clinical-filter editor are mounted in
dedicated hosts with cleanup; React does not modify their children. Patients
and Multimodal still use the same filter rules and explicit Apply action.

```bash
cd frontend
npm ci
npm run build
```

Edit `src/patients.jsx`, not `static/js/react/patients.js`. The generated bundle
and licence files are committed so native, Desktop and Docker launches need no
additional Node runtime or frontend build. No CDN or browser-side dependencies.

This is a contained experiment, not a migration of the rest of the application.
