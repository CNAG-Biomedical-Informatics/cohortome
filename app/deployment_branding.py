"""Optional secondary branding, shared by the deployment, not by a workspace."""
import base64
import binascii
import json
import struct
import zlib
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth import require_admin, require_authenticated
from app.config import STATE_ROOT_DIR
from app.state_io import advisory_file_lock, atomic_write_json

router = APIRouter(prefix='/deployment-branding', tags=['ui'])
EMPTY = {'name': '', 'website': '', 'logo': ''}
MAX_IMAGE_BYTES = 512 * 1024


class BrandingInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    website: str = Field(default='', max_length=2048)
    logo: str = Field(max_length=700000)


def validate_png(logo):
    try:
        if not logo.startswith('data:image/png;base64,'):
            raise ValueError('Use a PNG image.')
        data = base64.b64decode(logo.split(',', 1)[1], validate=True)
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError('The logo must be at most 512 KiB.')
        if data[:8] != b'\x89PNG\r\n\x1a\n':
            raise ValueError('Use a valid PNG image.')
        offset, chunks, compressed = 8, [], bytearray()
        while offset < len(data):
            size, kind = struct.unpack('>I4s', data[offset:offset + 8])
            end = offset + 12 + size
            if end > len(data): raise ValueError('Incomplete PNG image.')
            body = data[offset + 8:end - 4]
            crc = struct.unpack('>I', data[end - 4:end])[0]
            if zlib.crc32(kind + body) != crc: raise ValueError('Damaged PNG image.')
            if not chunks:
                if kind != b'IHDR' or size != 13: raise ValueError('Invalid PNG header.')
                width, height = struct.unpack('>II', body[:8])
                if not (0 < width <= 2048 and 0 < height <= 2048 and width * height <= 2097152):
                    raise ValueError('Use a logo up to 2048 pixels per side and 2 megapixels.')
            elif kind == b'IHDR': raise ValueError('Invalid PNG header.')
            if kind == b'acTL': raise ValueError('Use a still PNG, not an animated logo.')
            if kind == b'IDAT': compressed.extend(body)
            chunks.append(kind)
            offset = end
            if kind == b'IEND':
                if size or end != len(data): raise ValueError('Invalid PNG ending.')
                break
        if not chunks or chunks[-1] != b'IEND' or not compressed:
            raise ValueError('Incomplete PNG image.')
        decoder = zlib.decompressobj()
        decoder.decompress(bytes(compressed), 17 * 1024 * 1024)
        if not decoder.eof or decoder.unused_data:
            raise ValueError('Invalid or oversized PNG pixel data.')
    except (binascii.Error, struct.error, zlib.error) as exc:
        raise ValueError('Use a valid PNG image.') from exc


def read_branding():
    path = STATE_ROOT_DIR / 'deployment-branding.json'
    if not path.exists(): return dict(EMPTY)
    return json.loads(path.read_text(encoding='utf-8'))


def write_branding(value):
    path = STATE_ROOT_DIR / 'deployment-branding.json'
    with advisory_file_lock(path.with_suffix('.lock')):
        atomic_write_json(path, value, file_mode=0o600)
    return value


@router.get('')
def get_branding(request: Request):
    require_authenticated(request)
    return read_branding()


@router.put('')
def save_branding(payload: BrandingInput, request: Request):
    require_admin(request)
    name, website = payload.name.strip(), payload.website.strip()
    try:
        if not name: raise ValueError('Enter the deployment or programme name.')
        if website:
            url = urlsplit(website)
            if (url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password
                    or any(c.isspace() or ord(c) < 32 for c in website) or '\\' in website):
                raise ValueError('Use a complete HTTP or HTTPS website link without credentials.')
        validate_png(payload.logo)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return write_branding({'name': name, 'website': website, 'logo': payload.logo})


@router.delete('')
def remove_branding(request: Request):
    require_admin(request)
    return write_branding(dict(EMPTY))
