"""Copy only reviewed source files to the known TV box and install an isolated venv."""
import io
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tv_box import ssh_args

FILES = ['__init__.py', 'app.py', 'bulbs.py', 'fulfillment.py', 'manage.py',
         'oauth_store.py', 'requirements.txt', 'test_gateway.py', 'check.py',
         'control_check.py', 'publish_test.py', 'check_public.py']


def main():
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as archive:
        for name in FILES:
            archive.add(ROOT / 'gateway' / name, arcname='gateway/' + name)
        archive.add(ROOT / 'devices.json', arcname='devices.json')
    # Archive has only the explicit files above, no credentials or virtualenvs.
    subprocess.run(ssh_args() + [
        'umask 077; mkdir -p "$HOME/.smart-bulb-bridge/gateway-app" && '
        'tar -xf - -C "$HOME/.smart-bulb-bridge/gateway-app"'],
        input=stream.getvalue(), check=True, timeout=30)
    script = '''set -eu
umask 077
cd "$HOME/.smart-bulb-bridge"
bridge_python="$HOME/.smart-bulb-bridge/gateway-venv/bin/python"
if [ ! -x "$bridge_python" ]; then python -m venv gateway-venv; fi
"$bridge_python" -m pip install --no-input -r gateway-app/gateway/requirements.txt
cd gateway-app
"$bridge_python" -m unittest gateway.test_gateway -v
if [ ! -f ../gateway-private/config.json ]; then
    "$bridge_python" -m gateway.manage init --devices devices.json
fi
"$bridge_python" -m gateway.manage status
'''
    subprocess.run(ssh_args() + ['bash -s'], input=script, text=True, check=True, timeout=240)


if __name__ == '__main__':
    main()
