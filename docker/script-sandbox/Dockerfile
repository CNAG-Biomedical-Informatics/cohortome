FROM python:3.11-slim-bookworm
RUN pip install --no-cache-dir numpy==2.2.6 pandas==2.2.3 scipy==1.15.3 matplotlib==3.10.3 statsmodels==0.14.4
RUN apt-get update && apt-get install -y --no-install-recommends r-base-core r-bioc-limma r-bioc-edger r-cran-ggplot2 && rm -rf /var/lib/apt/lists/*
RUN Rscript --vanilla -e 'stopifnot(as.character(getRversion()) == "4.2.2", as.character(packageVersion("limma")) == "3.54.1", as.character(packageVersion("edgeR")) == "3.40.2", as.character(packageVersion("ggplot2")) == "3.4.1")'
COPY supervisor.py /opt/cohortome/supervisor.py
ENV MPLCONFIGDIR=/work/matplotlib OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
USER 65534:65534
WORKDIR /work
ENTRYPOINT ["python", "-I", "/opt/cohortome/supervisor.py"]
