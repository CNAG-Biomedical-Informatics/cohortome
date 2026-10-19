FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    R_LIBS_USER=/usr/local/lib/R/site-library \
    COHORTOME_PHENO_RANKER_BIN=/usr/local/bin/pheno-ranker

ARG PHENO_RANKER_SPEC=Pheno::Ranker

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      build-essential \
      ca-certificates \
      cpanminus \
      curl \
      git \
      libgsl-dev \
      libcurl4-openssl-dev \
      libfontconfig1-dev \
      libfreetype6-dev \
      libfribidi-dev \
      libharfbuzz-dev \
      libjpeg-dev \
      libpng-dev \
      libperl-dev \
      libssl-dev \
      libtiff5-dev \
      libxml2-dev \
      procps \
      r-base \
      r-base-dev \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /root/.R \
    && printf "CXX11STD = -std=gnu++14\n" > /root/.R/Makevars \
    && Rscript -e "cran <- c('BiocManager', 'jsonlite', 'ggplot2', 'msigdbr'); install.packages(cran, repos='https://cloud.r-project.org'); missing <- cran[!vapply(cran, requireNamespace, logical(1), quietly=TRUE)]; if (length(missing)) stop('Missing CRAN packages: ', paste(missing, collapse=', '))" \
    && Rscript -e "bioc <- c('DESeq2', 'apeglm', 'fgsea', 'limma', 'edgeR'); BiocManager::install(bioc, ask=FALSE, update=FALSE); missing <- bioc[!vapply(bioc, requireNamespace, logical(1), quietly=TRUE)]; if (length(missing)) stop('Missing Bioconductor packages: ', paste(missing, collapse=', '))"

RUN cpanm --notest "$PHENO_RANKER_SPEC" \
    && test -x /usr/local/bin/pheno-ranker \
    && rm -rf /root/.cpanm

COPY pyproject.toml ./
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install .

COPY app ./app
COPY config ./config
COPY scripts ./scripts
COPY static ./static
COPY templates ./templates

RUN python scripts/generate_synthetic_autoimmune_demo.py

RUN mkdir -p /var/lib/cohortome \
    && useradd --create-home --shell /usr/sbin/nologin cohortome \
    && chown -R cohortome:cohortome /app /var/lib/cohortome

USER cohortome

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
