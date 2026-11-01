"""Serve only the Termux SSH bootstrap to the known TV box on the direct LAN."""
import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import socket
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lan import active_lan

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--box', default='192.168.1.199')
args = parser.parse_args()
lan = active_lan()
box = lan.check_host(args.box)
directory = Path(__file__).resolve().parent
public_key = (directory / 'private/mac-ed25519.pub').read_text().strip()
if not public_key.startswith('ssh-ed25519 '):
    raise SystemExit('Expected a public Ed25519 key')
payload = (directory / 'ssh-bootstrap.sh').read_text().replace(
    '__MAC_IP__', lan.address
).replace('__BOX_IP__', box).replace('__AUTHORIZED_KEY__', public_key).encode()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.client_address[0] not in {box, lan.address}:
            self.send_error(403)
            return
        if self.path != '/setup':
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        print(f'Served public-key bootstrap to {self.client_address[0]}', flush=True)


server = HTTPServer((lan.address, 8765), Handler)
if sys.platform == 'darwin':
    server.socket.setsockopt(socket.IPPROTO_IP, 25, socket.if_nametoindex(lan.interface))
print(f'Bootstrap ready: http://{lan.address}:8765/setup (TV box {box} only)', flush=True)
server.serve_forever()
