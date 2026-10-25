# Test layout

The **Build and test** GitHub workflow runs a selected core regression suite,
JavaScript checks and two Chromium UI tests on code pushes to `main` and pull
requests. It can also be started manually. It builds the Python wheel, not desktop
installers, and needs no live LLM, R, Perl or Redis service. Desktop packaging and
Docker integration remain separate workflows. This is not the full test suite.

`test_bff.py` covers clinical record normalization, grouping and the basic patient
API. The former mixed suite is split into feature modules:

- `test_auth_settings_integration.py` and `test_model_providers_integration.py`
- `test_datasets_integration.py` and `test_store_assays_integration.py`
- `test_query_clinical_integration.py` and `test_query_planning_integration.py`
- `test_analysis_integration.py` and `test_analysis_runners_integration.py`
- `test_jobs_integration.py`, `test_cohorts_sessions_integration.py` and
  `test_pheno_integration.py`

These contain the existing tests, including unit-level checks; the integration
suffix distinguishes them from the smaller focused regression modules. Shared
synthetic fixture writers and state-isolation helpers live in
`bff_test_helpers.py`. Test modules import the helpers explicitly, not one another.

Run the module relevant to the change, for example:

```bash
PYTHONPATH=.deps:. pytest tests/test_auth_settings_integration.py -q
PYTHONPATH=.deps:. pytest tests/test_ui_smoke.py -q -k timeline
```

`make test` still discovers all backend modules. Splitting the files does not
change what it runs. Use the full suite for integration milestones rather than
after every localized edit.
