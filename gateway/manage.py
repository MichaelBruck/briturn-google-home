"""Install-local management; never prints credentials or exposes a LAN listener."""
import argparse
import json
import os
from pathlib import Path
import secrets

from waitress import serve
from werkzeug.security import generate_password_hash

from gateway.app import create_app, load_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['init', 'serve', 'status', 'revoke'])
    parser.add_argument('--private-dir', type=Path,
                        default=Path.home() / '.smart-bulb-bridge/gateway-private')
    parser.add_argument('--devices', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    private = args.private_dir
    config_path = private / 'config.json'
    if args.command == 'init':
        private.mkdir(parents=True, exist_ok=True, mode=0o700)
        if config_path.exists():
            raise SystemExit('Configuration already exists; refusing to overwrite credentials.')
        if not args.devices:
            raise SystemExit('--devices is required for init')
        password = secrets.token_urlsafe(24)
        config = {
            'source_ip': '192.168.1.199', 'subnet': '192.168.1.0/24',
            'devices': json.loads(args.devices.read_text()), 'writes_enabled': False,
            'public_url': None, 'google_project_id': None,
            'owner_id': secrets.token_hex(16), 'session_secret': secrets.token_hex(32),
            'owner_password_hash': generate_password_hash(password, method='pbkdf2:sha256:600000'),
            'client_id': 'lights-' + secrets.token_hex(12),
            'client_secret': secrets.token_urlsafe(48),
        }
        config_path.write_text(json.dumps(config, indent=2) + '\n')
        (private / 'gateway-password.txt').write_text(password + '\n')
        print('Initialised private configuration; credentials were not printed.')
        return
    config = load_config(config_path)
    if args.command == 'status':
        from gateway.bulbs import Bulbs
        backend = Bulbs(config)
        print(json.dumps({key: backend.read(key) for key in backend.devices}, indent=2))
        return
    app = create_app(config)
    if args.command == 'revoke':
        app.extensions['gateway_store'].revoke_all()
        print('Revoked all local OAuth codes and tokens. Also unlink in Google account settings.')
        return
    serve(app, host='127.0.0.1', port=8766, threads=4, connection_limit=32,
          max_request_body_size=32768, channel_timeout=15, clear_untrusted_proxy_headers=True)


if __name__ == '__main__':
    main()
