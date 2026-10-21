# Reference data for synthetic fixtures

## HGNC gene symbols

`hgnc_protein_coding_symbols.tsv` contains 19,296 rows with `symbol`,
`ensembl_gene_id` and `name` columns. Fixture generators use these identifiers;
the expression values they generate are synthetic.

Source: [HUGO Gene Nomenclature Committee](https://www.genenames.org/download/).
HGNC releases its data under [CC0](https://www.genenames.org/about/license/)
(licence page checked 21 October 2026).

The file entered this repository in commit `c3c388c` on 24 April 2026. The exact
upstream download date, release and extraction command were not recorded; do not
treat the Git date as the HGNC release date or claim that this is a current,
complete gene catalogue. A future refresh should record the upstream snapshot
and transformation command explicitly.

SHA-256: `2bf998a8c0584fa4a600ef9aaa7a3a77fbb60cbf4ff1eb2b4c7ba420b4498352`.

## Synthetic subject ClarIDs

`generate_synthetic_clarids.py` extends the ClarID 0.04 reference codebook with
four COHORTome synthetic study entries: COH-SYN (default), COH-PRIV (private),
COH-LARGE (large) and COH-AUTO (autoimmune). Human ClarIDs render these hyphens
as underscores, for example `COH_AUTO-30001-Case-M06.9-Male-A20_29`.
Their stub prefixes are CSD, CSP, CSL and CSA respectively. These are local
study entries, not additions to the upstream ClarID reference vocabulary.

The generator writes its extended `clarid-codebook.yaml` alongside the generated
CSVs. Retain that codebook when decoding these IDs with clarid-tools. COHORTome
itself reads the stored decoded fields and condition names; it does not need
clarid-tools at runtime.

Patient IDs and numeric subject IDs do not change. Human and stub ClarIDs differ
from the former CNAG-Test identifiers. Regenerate resource archives and rebuild
existing prepared fixture stores before expecting those copies to show new IDs.

`synthetic_autoimmune_clarid_subjects.csv` is the reviewed sidecar copied by the
autoimmune fixture generator. Keep it identical to the generated dataset sidecar.
