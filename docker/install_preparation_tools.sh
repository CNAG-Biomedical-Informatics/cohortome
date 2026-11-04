#!/bin/sh
# Match the released preparation tools in desktop/build_unix_pheno.py.
set -eu

preparation_build_dir=$(mktemp -d)
trap 'rm -rf -- "$preparation_build_dir"' EXIT
export PERL_CPANM_HOME="$preparation_build_dir/cpanm"
cd "$preparation_build_dir"

curl --fail --location --retry 4 --output Convert-Pheno-0.35.tar.gz \
  https://cpan.metacpan.org/authors/id/M/MR/MRUEDA/Convert-Pheno-0.35.tar.gz
curl --fail --location --retry 4 --output ClarID-Tools-0.05.tar.gz \
  https://cpan.metacpan.org/authors/id/M/MR/MRUEDA/ClarID-Tools-0.05.tar.gz
printf '%s\n' \
  'e39cfd33b4c297ef1f16c27588915a32463dc4d8d9d7ae1c57981bfd7e44be0a  Convert-Pheno-0.35.tar.gz' \
  '877a6bdadf64772055f250e410f10979b8afc1a0da7a33280e0df9c9129f7e39  ClarID-Tools-0.05.tar.gz' \
  | sha256sum --check --strict

cpanm --notest --mirror https://cpan.metacpan.org --mirror-only \
  File::HomeDir ./Convert-Pheno-0.35.tar.gz ./ClarID-Tools-0.05.tar.gz
test -x /usr/local/bin/convert-pheno
test -x /usr/local/bin/clarid-tools
perl -MConvert::Pheno -MClarID::Tools -e \
  'die "Unexpected preparation-tool version\n" unless $Convert::Pheno::VERSION eq "0.35" && $ClarID::Tools::VERSION eq "0.05"'

# Keep a stable, readable codebook path, independent of Perl's installation layout.
clarid_book=$(perl -MClarID::Tools -e 'print "$ClarID::Tools::share_dir/versions/0.04/clarid-codebook.yaml"')
install -D -m 0644 "$clarid_book" /usr/local/share/cohortome/clarid-codebook.yaml

# Retain the released sources and their notices, as for the desktop bundles.
install -d /usr/local/share/cohortome/sources /usr/local/share/cohortome/licenses
for distribution in Convert-Pheno-0.35 ClarID-Tools-0.05; do
  install -m 0644 "$distribution.tar.gz" /usr/local/share/cohortome/sources/
  tar -xzf "$distribution.tar.gz"
  install -d "/usr/local/share/cohortome/licenses/$distribution"
  for notice in LICENSE README META.json; do
    if test -f "$distribution/$notice"; then
      install -m 0644 "$distribution/$notice" "/usr/local/share/cohortome/licenses/$distribution/"
    fi
  done
done
