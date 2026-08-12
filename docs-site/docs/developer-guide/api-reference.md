---
title: API Reference
sidebar_position: 2
---

# API Reference

COHORTome exposes a FastAPI-generated OpenAPI contract.

This gives you three useful entry points:

- A checked-in OpenAPI snapshot for documentation and tooling:
  [`cohortome-openapi.json`](/openapi/cohortome-openapi.json)
- The live OpenAPI schema from the running app:
  `/openapi.json`
- The live interactive API UIs from the running app:
  `/docs`
  `/redoc`

## What the schema covers

The current OpenAPI contract is strongest for the stable top-level API surfaces:

- authentication and local user visibility
- dataset registry and workspace selection
- patient list endpoints
- saved cohorts
- transcriptomics assay inventory
- multimodal assay readiness
- multimodal feature matrix preview
- DICOM study discovery and integration status
- selected delete/update helpers

More dynamic endpoints such as free-form `Query`, `Analysis`, and some `Pheno-Ranker`
result payloads are already tagged and described, but still have looser response
contracts. That is intentional for now while those response shapes are still evolving.

`POST /llm/general` is the context-free model endpoint used by the explicit
General-question mode in Query and Analysis. Its request contains a prompt and
recent General-question turns only; it does not resolve or serialize an active
workspace.

## Suggested uses

The OpenAPI schema is useful even if the browser UI remains the main interface:

- inspect the backend contract during development
- generate client code or typed SDKs later
- validate route changes during refactors
- document integrations without duplicating endpoint details by hand

## Regenerating the checked-in snapshot

From the repository root:

```bash
python3 - <<'PY'
import json
from pathlib import Path
from app.main import app

placeholder = "/path/to/cohortome/default_dataset"
absolute_default = str((Path.cwd() / "default_dataset").resolve())

def clean(value):
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean(item) for item in value]
    if isinstance(value, str):
        return value.replace(absolute_default, placeholder)
    return value

path = Path("docs-site/static/openapi")
path.mkdir(parents=True, exist_ok=True)
(path / "cohortome-openapi.json").write_text(
    json.dumps(clean(app.openapi()), indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)
PY
```

If the API changes materially, regenerate this snapshot so the Docusaurus copy stays in
sync with the running FastAPI app.
