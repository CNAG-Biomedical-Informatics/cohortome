# Third-party software and data

COHORTome code is licensed under [Apache-2.0](LICENSE). Third-party software
and reference data retain their own licences and copyright notices.

## Files in this source repository

- The gene-symbol table is derived from HUGO Gene Nomenclature Committee
  (HGNC) data, released under [CC0](https://www.genenames.org/about/license/).
  File provenance is recorded in [scripts/data/README.md](scripts/data/README.md).
- Current DICOM fixtures are procedural COHORTome phantoms. Historical revisions
  used pydicom's `MR_small.dcm` test pixels. The retained
  [pydicom 3.0.2 licence](licenses/pydicom-3.0.2.txt) credits Darcy Mason and
  pydicom contributors and includes the GDCM notice for generated dictionaries.

## Software components

- Plotly.js and Cytoscape.js provide interactive plots and networks. The desktop
  packager retains their package licence files under `static/vendor/`.
- The shared Perl runtime provides Pheno-Ranker, Convert-Pheno and ClarID tools.
  Its builder retains their top-level notices under `licenses/` and downloaded
  source archives under `sources/` within that runtime.
- OHIF provides DICOM viewing under an [MIT licence](https://github.com/OHIF/Viewers).
  Desktop workflows and the Docker build include pinned static viewer assets.
  Desktop package manifests record the source image and asset checksums.
  Viewer dependency notices remain part of the binary redistribution review.

Python, Rust/Tauri, Perl, R and their libraries remain subject to their respective
terms. The components included depend on the distribution. Settings reports
detected versions; the licence texts accompanying each distribution govern its
included components.

## Imported data and terminology

Imported study data, terminology databases and downloaded gene sets are not
relicensed by COHORTome. Their source-specific terms apply independently of
the software used to process them.

For binary-distribution review requirements, see
[Desktop packaging](desktop/PACKAGING.md#redistribution-review).
