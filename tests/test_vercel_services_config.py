import json
from pathlib import Path


def test_vercel_services_use_authoritative_backend_only():
    config = json.loads(Path(__file__).resolve().parents[1].joinpath('vercel.json').read_text(encoding='utf-8'))
    services = config.get('services', {})

    assert set(services.keys()) == {'api', 'web'}
    assert services['api']['root'] == 'apps/api'
    assert services['web']['root'] == 'apps/web'

    rewrites = config.get('rewrites', [])
    assert any(r.get('source') == '/api/(.*)' and r.get('destination', {}).get('service') == 'api' for r in rewrites)
    assert any(r.get('source') == '/(.*)' and r.get('destination', {}).get('service') == 'web' for r in rewrites)

    assert 'app' not in services
