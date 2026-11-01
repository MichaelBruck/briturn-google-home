"""Read-only upstream discovery and checksum-validated state queries."""
import argparse
from datetime import datetime
import json
from pathlib import Path

from lan import LANBulb, LANScanner, active_lan, snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout', type=int, default=8, choices=range(2, 31))
    parser.add_argument('--host', help='Optional single directly connected host')
    args = parser.parse_args()
    lan = active_lan()
    scanner = LANScanner(lan)
    print(f'Read-only discovery: {lan.interface} {lan.address} {lan.subnet}', flush=True)
    found = scanner.discover(args.timeout, args.host)
    report = {
        'time': datetime.now().astimezone().isoformat(),
        'lan': {'interface': lan.interface, 'address': lan.address, 'subnet': str(lan.subnet)},
        'discovery': found, 'udp_replies': scanner.replies, 'devices': [],
    }
    for discovery in found:
        bulb = None
        try:
            bulb = LANBulb(lan, discovery['ipaddr'], discovery)
            state = snapshot(bulb)
            state['sent_frames'] = bulb.frames_sent
            report['devices'].append(state)
            print(json.dumps(state, indent=2))
        except Exception as exc:
            report['devices'].append({'ip': discovery['ipaddr'], 'error': str(exc)})
        finally:
            if bulb:
                bulb.close()
    Path('diagnostics').mkdir(exist_ok=True)
    path = Path('diagnostics') / f'discovery-{datetime.now().strftime("%Y%m%d-%H%M%S")}.json'
    path.write_text(json.dumps(report, indent=2, default=str) + '\n')
    print(f'Saved {path}; {len(found)} discovery candidates')


if __name__ == '__main__':
    main()
