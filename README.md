<p align="center">
  <img src="docs-site/static/img/cohortome-logo.svg" width="96" alt="COHORTome logo">
</p>

<h1 align="center">COHORTome</h1>

[![Version](https://img.shields.io/badge/version-0.1.0-blue)](CHANGELOG.md)
[![License](https://img.shields.io/badge/license-Apache--2.0-0298c3)](LICENSE)
[![Build and test](https://github.com/CNAG-Biomedical-Informatics/cohortome/actions/workflows/build-and-test.yml/badge.svg?branch=main)](https://github.com/CNAG-Biomedical-Informatics/cohortome/actions/workflows/build-and-test.yml)
[![Desktop build](https://img.shields.io/github/actions/workflow/status/CNAG-Biomedical-Informatics/cohortome/desktop-release-draft.yml?branch=main&label=Desktop%20build)](https://github.com/CNAG-Biomedical-Informatics/cohortome/actions/workflows/desktop-release-draft.yml)
[![Docker Hub pulls](https://img.shields.io/docker/pulls/manuelrueda/cohortome?label=Docker%20Hub)](https://hub.docker.com/r/manuelrueda/cohortome)
[![Documentation](https://github.com/CNAG-Biomedical-Informatics/cohortome/actions/workflows/docs-pages.yml/badge.svg?branch=main)](https://github.com/CNAG-Biomedical-Informatics/cohortome/actions/workflows/docs-pages.yml)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23638366.svg)](https://doi.org/10.5281/zenodo.23638366)

<p align="center">
  <a href="https://cnag-biomedical-informatics.github.io/cohortome/">📚 Documentation</a> ·
  <a href="https://cnag-biomedical-informatics.github.io/cohortome/docs/getting-started/desktop">📦 Desktop</a> ·
  <a href="https://cnag-biomedical-informatics.github.io/cohortome/docs/admin-guide/starting-and-stopping">🌐 Web deployment</a> ·
  <a href="https://cnag-biomedical-informatics.github.io/cohortome/docs/user-guide/user-journeys">🧭 User guide</a>
</p>

COHORTome is an open-source application for clinical and multimodal cohort
analysis. Explore patient records and assays, save cohorts, run analyses, and
inspect their plots and output files. Language models can help interpret
questions and explain results, but are optional.

![COHORTome dashboard using bundled synthetic data](docs-site/static/img/screenshots/workspace-shell.png)

## Get started

**Desktop is recommended for individual use.**
Follow the [installation guide](https://cnag-biomedical-informatics.github.io/cohortome/docs/getting-started/desktop)
for Linux, macOS and Windows installers or source setup.

**Web is for shared servers with user accounts and dataset permissions.**
Deploy the prebuilt [Docker Hub image](https://hub.docker.com/r/manuelrueda/cohortome)
with Compose on Linux amd64 or arm64; no local build is needed. See the
[Web deployment guide](https://cnag-biomedical-informatics.github.io/cohortome/docs/admin-guide/starting-and-stopping).

Start with the bundled synthetic datasets and
[user journeys](https://cnag-biomedical-informatics.github.io/cohortome/docs/user-guide/user-journeys).
Synthetic results demonstrate software behaviour, not biological findings.

## Citation

Rueda et al. *COHORTome: an open-source application for clinical and multimodal
cohort analysis.* **Manuscript in preparation.**

Software: Rueda, M. (2026). *COHORTome* [Software]. Zenodo.
[doi:10.5281/zenodo.23638366](https://doi.org/10.5281/zenodo.23638366).
This DOI covers all versions; include the version used in your work. See
[citation details](https://cnag-biomedical-informatics.github.io/cohortome/docs/about/citation).

Funding and institutional support are listed in
[Acknowledgements](https://cnag-biomedical-informatics.github.io/cohortome/docs/about/acknowledgements).

Licensed under [Apache-2.0](LICENSE). See [NOTICE](NOTICE).

COHORTome is research software, not a clinical decision system.
For dependency and reference-data terms, see
[Third-party notices](THIRD_PARTY_NOTICES.md). Report vulnerabilities privately
using the [security policy](SECURITY.md).
