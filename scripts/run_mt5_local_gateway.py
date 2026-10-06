"""Loopback-only terminal opener. No credentials, trading or arbitrary commands."""
import argparse
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api'))
from app.domain.mt5_terminal_launcher import launch_terminal
from app.domain.mt5_terminal_discovery import normalize_terminal_exe
from app.domain.mt5_windows_worker import WindowsBridge

ORIGINS = {'https://cacsms-traders.vercel.app', 'http://localhost:5173', 'http://127.0.0.1:5173'}


def handler_for(terminal, bridge=None):
    lock = threading.Lock()
    bridge = bridge or WindowsBridge(terminal)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            if sys.stderr is not None:
                super().log_message(format,*args)

        def allowed(self):
            return self.headers.get('Host') == '127.0.0.1:8917' and self.headers.get('Origin') in ORIGINS

        def reply(self, status, data):
            body = json.dumps(data).encode()
            self.send_response(status)
            if self.allowed():
                self.send_header('Access-Control-Allow-Origin', self.headers['Origin'])
                self.send_header('Vary', 'Origin')
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == '/health' and self.headers.get('Host') == '127.0.0.1:8917':
                self.reply(200, {'ok': True, 'service': 'cacsms-mt5-local', 'bridge_supported': True})
            else:
                self.reply(403, {'ok': False})

        def do_OPTIONS(self):
            if not self.allowed() or self.path not in ('/terminal/open','/bridge/connect'):
                self.reply(403, {'ok': False})
                return
            self.send_response(204)
            self.send_header('Access-Control-Allow-Origin', self.headers['Origin'])
            self.send_header('Vary', 'Origin')
            self.send_header('Access-Control-Allow-Methods', 'POST')
            self.send_header('Access-Control-Allow-Headers', 'X-Cacsms-MT5, Content-Type')
            self.send_header('Access-Control-Allow-Private-Network', 'true')
            self.end_headers()

        def do_POST(self):
            if self.path == '/bridge/connect' and self.allowed() and self.headers.get('X-Cacsms-MT5') == 'connect':
                try:
                    length = int(self.headers.get('Content-Length','0'))
                    if not 0 < length <= 1024 or self.headers.get('Transfer-Encoding'):
                        raise ValueError('Invalid pairing request size')
                    body = json.loads(self.rfile.read(length))
                    if body.get('origin') not in ('https://cacsms-traders.vercel.app', 'http://localhost:8000', 'http://127.0.0.1:8000'):
                        raise ValueError('Invalid cloud origin')
                    if self.headers['Origin'] == 'https://cacsms-traders.vercel.app' and body['origin'] != self.headers['Origin']:
                        raise ValueError('Cloud origin does not match website')
                    with lock:
                        result = bridge.connect(body['tenant_id'],body['token'],body['origin'])
                    self.reply(200,result)
                except (ValueError,KeyError,RuntimeError,ImportError) as exc:
                    self.reply(503,{'ok':False,'error':str(exc)})
                return
            if not self.allowed() or self.path != '/terminal/open' or self.headers.get('X-Cacsms-MT5') != 'open' or self.headers.get('Content-Length', '0') != '0':
                self.reply(403, {'ok': False, 'error': 'Request refused'})
                return
            with lock:
                result = launch_terminal(terminal)
            self.reply(200 if result['ok'] else 503, {key: value for key, value in result.items() if key != 'path'})

    return Handler


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--terminal-path', required=True)
    args = parser.parse_args()
    terminal = normalize_terminal_exe(args.terminal_path)
    if not terminal or Path(terminal).name.lower() != 'terminal64.exe':
        parser.error('An installed terminal64.exe is required')
    ThreadingHTTPServer(('127.0.0.1', 8917), handler_for(terminal)).serve_forever()
