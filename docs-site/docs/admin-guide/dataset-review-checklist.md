# Dataset review checklist

Use this before proposing a Store recipe or sharing an importable package.
Record the outcome beside the dataset recipe. A structural validation pass is
not scientific validation or permission to redistribute data.

## Source and permissions

- [ ] Identify the study, exact input products, retrieval date and checksums.
- [ ] Record access/use conditions, attribution and separate redistribution status.
- [ ] Check annotation and terminology sources as well as the primary data.
- [ ] Exclude credentials, private access details and restricted records from Git.

## Mapping and linkage

- [ ] Distinguish patients, visits, specimens and technical/biological replicates.
- [ ] Account for every source column, including exclusions and unresolved meanings.
- [ ] Review ontology terms, units, negative findings and missing-value conventions.
- [ ] Keep longitudinal clinical snapshots distinct; preserve explicit sample links.
- [ ] Remove converter placeholders that are not observations; do not invent dates.
- [ ] Declare each assay's feature namespace, value scale and upstream processing.
- [ ] If ClarIDs are included, preserve original IDs and review their source fields.

## Package and checks

- [ ] Record converter/mapping versions, preparation recipe and validator revision.
- [ ] Run the package validator; review warnings and separate BFF/terminology checks.
- [ ] Include the dataset manifest, clinical records and any declared assay files.
- [ ] For ZIP import, include `resource.json` and exactly one dataset-root folder.
- [ ] Record file/archive checksums; exclude DuckDB caches, accounts and user state.
- [ ] Confirm expected patient, visit, sample and feature counts after a clean import.
- [ ] Inspect clinical fields and assay availability in the app; document limitations.
- [ ] Use a new resource version for changed published contents; do not replace archives.

## Review outcome

Record the reviewer, date, tested COHORTome version, aggregate counts and open
issues. State separately whether the **recipe** can be shared, whether the
**data archive** can be redistributed, and which **analyses** are appropriate.
A compatible format does not make studies scientifically comparable.
