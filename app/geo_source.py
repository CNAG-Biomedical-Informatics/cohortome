"""Reviewed GEO source downloads. No user URLs or remotely supplied recipes."""
import hashlib
import shutil
from urllib.parse import urljoin, urlparse

import httpx


GSE85034 = {
    "accession": "GSE85034",
    "recipe_version": 1,
    "url": "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE85nnn/GSE85034/matrix/GSE85034_series_matrix.txt.gz",
    "bytes": 42972187,
    "sha256": "786101c84b027d91782616d290a34f2bc94ad60f8ca251d97d744032fa3d667f",
}


class SourcePreparationError(ValueError):
    """Safe, record-free explanation suitable for installation status."""


def source_url(client, url):
    """Resolve only Hugging Face's fixed-source CDN hops; never send credentials."""
    if urlparse(url).hostname != 'huggingface.co':
        return url
    for _ in range(5):
        response = client.head(url)
        if response.status_code == 200:
            return url
        if not response.is_redirect:
            raise SourcePreparationError('Harmonized source download is unavailable.')
        url = urljoin(url, response.headers.get('location', ''))
        parsed = urlparse(url)
        host = parsed.hostname or ''
        if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443)
                or not (host == 'huggingface.co' or host.endswith('.huggingface.co') or host.endswith('.hf.co'))):
            raise SourcePreparationError('Unexpected source download redirect.')
    raise SourcePreparationError('Too many source download redirects.')


def verify_source(path, spec=None):
    spec = GSE85034 if spec is None else spec
    with path.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    if path.stat().st_size != spec["bytes"] or digest != spec["sha256"]:
        raise SourcePreparationError("Source differs from the reviewed release. No data were imported.")
    return digest


def fetch_source(target, *, spec=None, check_cancel=lambda: None, report=lambda **kw: None):
    """Download one fixed HTTPS product, bounded by its reviewed size/hash."""
    spec = GSE85034 if spec is None else spec
    if shutil.disk_usage(target.parent).free < spec["bytes"] + 1024**3:
        raise SourcePreparationError("Not enough free space to download and prepare this dataset.")
    check_cancel()
    # Deliberately do not follow redirects or send GitHub credentials to GEO.
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        with client.stream("GET", source_url(client, spec["url"])) as response:
            if response.status_code != 200:
                raise SourcePreparationError("Source download is unavailable. Please retry later.")
            owned = False
            try:
                with target.open("xb") as output:
                    owned = True
                    size = 0
                    for chunk in response.iter_bytes(1024 * 1024):
                        check_cancel()
                        size += len(chunk)
                        if size > spec["bytes"]:
                            raise SourcePreparationError("Source download exceeds the reviewed source size.")
                        output.write(chunk)
                        report(bytes=size, total=spec["bytes"])
                verify_source(target, spec)
            except BaseException:
                if owned:
                    target.unlink(missing_ok=True)
                raise
    return target
