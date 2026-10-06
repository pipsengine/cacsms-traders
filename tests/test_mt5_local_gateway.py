import importlib.util
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path


def test_gateway_restricts_origin_header_and_path(monkeypatch):
    spec = importlib.util.spec_from_file_location('mt5_local_gateway', Path(__file__).resolve().parents[1] / 'scripts/run_mt5_local_gateway.py')
    gateway = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gateway)
    calls = []
    monkeypatch.setattr(gateway, 'launch_terminal', lambda path: calls.append(path) or {'ok': True, 'launched': True})
    server = ThreadingHTTPServer(('127.0.0.1', 0), gateway.handler_for('fixed-terminal'))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def request(origin, marker='open', path='/terminal/open', host='127.0.0.1:8917'):
        connection = HTTPConnection('127.0.0.1', server.server_port, timeout=3)
        connection.request('POST', path, headers={'Host': host, 'Origin': origin, 'X-Cacsms-MT5': marker})
        response = connection.getresponse()
        status = response.status
        response.read()
        connection.close()
        return status
    try:
        assert request('https://unrelated.example') == 403
        assert request('https://cacsms-traders.vercel.app', marker='') == 403
        assert request('https://cacsms-traders.vercel.app', path='/other') == 403
        assert request('https://cacsms-traders.vercel.app', host='attacker.example:8917') == 403
        assert calls == []
        assert request('https://cacsms-traders.vercel.app') == 200
        assert calls == ['fixed-terminal']
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
