"""Fallback: TCP 5577 only, bounded to the active directly connected LAN."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
from pathlib import Path
import socket

from lan import active_lan, bind_lan, LANBulb, snapshot


def main():
    lan = active_lan()
    if lan.subnet.num_addresses > 256:
        raise SystemExit('Refusing an automatic scan larger than /24')

    def probe(ip):
        if str(ip) == lan.address:
            return None
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            bind_lan(sock, lan)
            sock.settimeout(2)
            try:
                sock.connect((str(ip), 5577))
                return {'ip': str(ip), 'result': 'open'}
            except OSError as exc:
                return {'ip': str(ip), 'result': type(exc).__name__, 'errno': exc.errno}

    with ThreadPoolExecutor(max_workers=16) as pool:
        ports = [r for r in pool.map(probe, lan.subnet.hosts()) if r]
    devices = []
    for item in ports:
        if item['result'] != 'open':
            continue
        bulb = None
        try:
            bulb = LANBulb(lan, item['ip'])
            device = snapshot(bulb)
            device['sent_frames'] = bulb.frames_sent
            devices.append(device)
        except Exception as exc:
            devices.append({'ip': item['ip'], 'query_error': str(exc)})
        finally:
            if bulb:
                bulb.close()
    report = {'time': datetime.now().astimezone().isoformat(), 'subnet': str(lan.subnet),
              'port': 5577, 'ports': ports, 'devices': devices}
    Path('diagnostics').mkdir(exist_ok=True)
    path = Path('diagnostics') / f'tcp5577-{datetime.now().strftime("%Y%m%d-%H%M%S")}.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(devices, indent=2))
    from collections import Counter
    print(dict(Counter(p['result'] for p in ports)))
    print(f'Saved {path}')


if __name__ == '__main__':
    main()
