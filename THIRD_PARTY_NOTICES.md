# Third-party software and data

COHORTome code is licensed under Apache-2.0. Dependencies and reference data
retain their own licences. A list of component versions in Settings is not a
replacement for the licence texts supplied with a distribution.

## Files in this source repository

- The vendored HGNC gene-symbol table uses CC0 data. Its columns, checksum and
  provenance limitations are recorded in [scripts/data/README.md](scripts/data/README.md).
- Current DICOM fixtures are procedural COHORTome phantoms. Historical revisions
  used pydicom's `MR_small.dcm` test pixels. Preserve that historical attribution;
  see the retained [pydicom 3.0.2 licence](licenses/pydicom-3.0.2.txt), including
  its GDCM notice. Older distributions must retain their version's notices too.
- Bundled synthetic clinical and assay fixtures demonstrate software behaviour.
  Imported study data are separate and are not relicensed by COHORTome.

## Desktop distributions

The experimental packager retains the Plotly and Cytoscape package licence files.
The shared Perl builder retains the top-level tool notices and downloaded source
archives. Neither step is a complete review of transitive dependencies.

Before distributing a binary bundle, inspect the exact artifact and provide:

- Python and all included Python-package licence texts, including the scientific
  stack and any native libraries collected by the freezer;
- Rust/Tauri dependency notices for the locked dependency graph;
- Perl, CPAN module and copied native-library notices and any required sources;
- R, Bioconductor/CRAN package and copied native-library notices and any required
  corresponding sources;
- viewer and browser-library notices if OHIF assets are included;
- separate provenance and applicable terms for terminology databases shipped by
  Convert-Pheno and ClarID, including their exact vocabulary editions.

Do not infer permission for a terminology database from the software licence of
the tool that includes it. In particular, identify the actual ICD edition and
source before applying [WHO's classification terms](https://www.who.int/about/policies/publishing/copyright).

OHIF assets are currently prepared separately and are not included by the desktop
packager. OHIF itself uses an [MIT licence](https://github.com/OHIF/Viewers);
its dependency notices must also accompany a redistributed viewer build.
MSigDB gene sets are not part of the synthetic packaging tests. Installing
`msigdbr` does not establish permission to redistribute its downloaded data.

**Binary redistribution review is not complete.** Experimental CI artifacts are
not approved release downloads. Publishing source code does not clear existing
CI artifacts for distribution; review or remove those artifacts before changing
repository visibility. Keep required sources and notices with each approved
release, rather than relying on expiring CI artifacts.
