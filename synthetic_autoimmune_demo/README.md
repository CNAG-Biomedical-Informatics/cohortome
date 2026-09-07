# Synthetic autoimmune demo — not real PRECISESADS data

90 independently fictional participants: 30 RA, 30 SLE, 30 healthy controls.
Clinical data link to simulated RNA, methylation, immune-cell and serology
measurements. No real study records or patient-derived distributions were used.

See `docs-site/docs/user-guide/synthetic-autoimmune-demo.md` for a walkthrough,
simulation assumptions and limitations. `provenance.json` records the seed;
`simulation_truth.json` identifies planted effects. These are software test
signals, not biological findings. RNA values are expected-count-like simulations,
not outputs of RSEM. CpG identifiers are fictional and cannot be annotated.

Regenerate into a **new** directory with:

```bash
python3 scripts/generate_synthetic_autoimmune_demo.py --output /tmp/autoimmune-demo
```

Distribute this dataset with a clean installation, never a research runtime.
