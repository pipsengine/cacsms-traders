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

ORIGINS = {'https://cacsms-traders.vercel.app', 'http://localhost:5173', 'http://127.0.0.1:5173'}


def handler_for(terminal):
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
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
                self.reply(200, {'ok': True, 'service': 'cacsms-mt5-local'})
            else:
                self.reply(403, {'ok': False})

        def do_OPTIONS(self):
            if not self.allowed() or self.path != '/terminal/open':
                self.reply(403, {'ok': False})
                return
            self.send_response(204)
            self.send_header('Access-Control-Allow-Origin', self.headers['Origin'])
            self.send_header('Vary', 'Origin')
            self.send_header('Access-Control-Allow-Methods', 'POST')
            self.send_header('Access-Control-Allow-Headers', 'X-Cacsms-MT5')
            self.send_header('Access-Control-Allow-Private-Network', 'true')
            self.end_headers()

        def do_POST(self):
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
