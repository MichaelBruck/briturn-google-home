"""Explicit operator action: publish the already tested gateway through a Quick Tunnel.

Run only after approval for public exposure. No DNS changes, autostart or bulb
writes. Private configuration and tunnel logs stay on the TV box.
"""
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
import urllib.request


ROOT = Path.home() / '.smart-bulb-bridge'
PRIVATE = ROOT / 'gateway-private'


def command(pid):
    try:
        return Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
    except FileNotFoundError:
        return []


def stop_gateway():
    path = PRIVATE / 'gateway.pid'
    if not path.exists():
        return
    pid = int(path.read_text())
    args = command(pid)
    if not args:
        return
    if b'gateway.manage' not in args or b'serve' not in args:
        raise RuntimeError('Saved PID is not the gateway; refusing to signal it')
    os.kill(pid, signal.SIGTERM)
    for _ in range(50):
        if command(pid) != args:
            return
        time.sleep(0.1)
    raise RuntimeError('Old gateway did not stop')


def start_gateway():
    with (PRIVATE / 'gateway.log').open('ab') as log:
        proc = subprocess.Popen([str(ROOT / 'gateway-venv/bin/python'),
            '-m', 'gateway.manage', 'serve'], cwd=ROOT / 'gateway-app',
            stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    (PRIVATE / 'gateway.pid').write_text(str(proc.pid) + '\n')
    for _ in range(50):
        if proc.poll() is not None:
            raise RuntimeError('Gateway failed to start; inspect its private log')
        try:
            health = json.loads(urllib.request.urlopen(
                'http://127.0.0.1:8766/healthz', timeout=1).read())
            if health['account_linking_configured']:
                return proc.pid
        except OSError:
            pass
        time.sleep(0.2)
    raise RuntimeError('Configured gateway did not become healthy')


def main():
    os.umask(0o077)
    config_path = PRIVATE / 'config.json'
    config = json.loads(config_path.read_text())
    if config.get('google_project_id') != 'my-lights-project':
        raise RuntimeError('Unexpected Google project')
    if config.get('public_url'):
        raise RuntimeError('A public origin is already configured; inspect it before creating another tunnel')
    old_config = config_path.read_text()
    log_path = PRIVATE / 'tunnel.log'
    with log_path.open('wb') as log:
        tunnel = subprocess.Popen(['cloudflared', 'tunnel', '--no-autoupdate',
            '--url', 'http://127.0.0.1:8766',
            '--metrics', '127.0.0.1:20242'], stdin=subprocess.DEVNULL,
            stdout=log, stderr=log, start_new_session=True)
    (PRIVATE / 'tunnel.pid').write_text(str(tunnel.pid) + '\n')
    try:
        origin = None
        for _ in range(120):
            if tunnel.poll() is not None:
                raise RuntimeError('Tunnel exited; inspect private tunnel log')
            match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com\b', log_path.read_text())
            if match:
                origin = match[0]
                break
            time.sleep(0.5)
        if not origin:
            raise RuntimeError('Tunnel did not allocate an HTTPS hostname')
        config['public_url'] = origin
        config['writes_enabled'] = False
        next_path = PRIVATE / 'config.next'
        next_path.write_text(json.dumps(config, indent=2) + '\n')
        next_path.chmod(0o600)
        next_path.replace(config_path)
        stop_gateway()
        gateway_pid = start_gateway()
        print(json.dumps({'public_url': origin, 'google_project_id': config['google_project_id'],
            'tunnel_pid': tunnel.pid, 'gateway_pid': gateway_pid,
            'physical_writes_enabled': False, 'temporary_test_only': True}, indent=2))
    except Exception:
        tunnel.terminate()
        tunnel.wait(timeout=10)
        config_path.write_text(old_config)
        config_path.chmod(0o600)
        raise


if __name__ == '__main__':
    main()
