"""Read-only diagnostics for the Termux bulb clients and gateway over pinned SSH."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def ssh_args():
    private = ROOT / 'tv-box-install/private'
    return [
        'ssh', '-i', str(private / 'mac-ed25519'),
        '-o', 'IdentitiesOnly=yes',
        '-o', f'UserKnownHostsFile={private / "box-known-hosts"}',
        '-o', 'StrictHostKeyChecking=yes', '-o', 'BatchMode=yes',
        '-o', 'ConnectTimeout=5', '-o', 'ServerAliveInterval=10',
        '-o', 'ServerAliveCountMax=2', '-p', '8022', 'u0_a52@192.168.1.199',
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['status', 'inspect', 'gateway-status', 'gateway-health'])
    args = parser.parse_args()
    if args.command == 'status':
        command = '$HOME/.smart-bulb-bridge/venv/bin/python $HOME/.smart-bulb-bridge/read-bulbs.py'
        body = None
    elif args.command == 'gateway-status':
        command = 'cd "$HOME/.smart-bulb-bridge/gateway-app" && "$HOME/.smart-bulb-bridge/gateway-venv/bin/python" -m gateway.manage status'
        body = None
    elif args.command == 'gateway-health':
        command = "python -c 'import urllib.request; print(urllib.request.urlopen(\"http://127.0.0.1:8766/healthz\", timeout=5).read().decode())'"
        body = None
    else:
        command = 'bash -s'
        body = (ROOT / 'tv-box-install/inspect-box.sh').read_text()
    try:
        result = subprocess.run(ssh_args() + [command], input=body, text=True, timeout=60)
        return result.returncode
    except subprocess.TimeoutExpired:
        print('TV box command timed out. Check that Termux is open and the SSH server is running.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
