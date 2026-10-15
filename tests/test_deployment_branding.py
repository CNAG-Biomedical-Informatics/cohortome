import base64
import json
import struct
import zlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import deployment_branding as branding


def png(width=1, height=1):
    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
    data = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
    data += chunk(b'IDAT', zlib.compress(b'\x00\x00\x80\x80\xff')) + chunk(b'IEND', b'')
    return 'data:image/png;base64,' + base64.b64encode(data).decode()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(branding, 'STATE_ROOT_DIR', tmp_path)
    monkeypatch.setenv('COHORTOME_AUTH_MODE', 'none')
    app = FastAPI(); app.include_router(branding.router)
    return TestClient(app)


def test_save_read_replace_remove_persists(client, tmp_path):
    assert client.get('/deployment-branding').json() == branding.EMPTY
    payload = {'name': '3TR', 'website': 'https://example.org/', 'logo': png()}
    assert client.put('/deployment-branding', json=payload).status_code == 200
    assert client.get('/deployment-branding').json() == payload
    assert json.loads((tmp_path / 'deployment-branding.json').read_text()) == payload
    payload['name'] = 'Another programme'
    assert client.put('/deployment-branding', json=payload).json() == payload
    assert client.delete('/deployment-branding').json() == branding.EMPTY
    assert client.get('/deployment-branding').json() == branding.EMPTY


@pytest.mark.parametrize('website', ['javascript:alert(1)', '//example.org', 'https://u:p@example.org', 'https://a\\b', 'https://exa mple.org'])
def test_rejects_unsafe_links(client, website):
    assert client.put('/deployment-branding', json={'name': 'Test', 'website': website, 'logo': png()}).status_code == 400


@pytest.mark.parametrize('logo', ['data:image/svg+xml;base64,PHN2Zy8+', 'data:image/png;base64,AAAA', png(2049), png() + 'junk'])
def test_rejects_invalid_images(client, logo):
    assert client.put('/deployment-branding', json={'name': 'Test', 'logo': logo}).status_code == 400
    assert client.get('/deployment-branding').json() == branding.EMPTY


def test_admin_required_for_writes_and_login_for_read(client, monkeypatch):
    from fastapi import HTTPException
    def denied(_): raise HTTPException(403, 'Admin access required')
    monkeypatch.setattr(branding, 'require_admin', denied)
    assert client.put('/deployment-branding', json={'name': 'Test', 'logo': png()}).status_code == 403
    assert client.delete('/deployment-branding').status_code == 403
    assert client.get('/deployment-branding').status_code == 200
    def signed_out(_): raise HTTPException(401, 'Authentication required')
    monkeypatch.setattr(branding, 'require_authenticated', signed_out)
    assert client.get('/deployment-branding').status_code == 401
