"""Single-bulb CLI. Uses flux_led; never guesses a target or changes pairing."""
import argparse
import json
from pathlib import Path
import sys
import time

from flux_led.const import COLOR_MODE_CCT, COLOR_MODE_RGB, MODE_COLOR, MODE_WW
from lan import LANBulb, LANScanner, active_lan, snapshot


def bounded_int(low, high):
    def parse(value):
        number = int(value)
        if not low <= number <= high:
            raise argparse.ArgumentTypeError(f'must be between {low} and {high}')
        return number
    return parse


def check_control_support(bulb):
    if bulb.model_num != 0x35:
        raise ValueError(f'{bulb.model}: control is limited to confirmed model 0x35 RGBCW')
    if bulb.protocol not in {'LEDENET', 'LEDENET_AUTO_ON', 'LEDENET_DIMMABLE_EFFECTS', 'LEDENET_25_BYTE'}:
        raise ValueError(f'Control for {bulb.protocol} has not been validated in this project')
    if not {COLOR_MODE_RGB, COLOR_MODE_CCT}.issubset(bulb.color_modes):
        raise ValueError('Device did not identify both RGB and CCT capabilities')


def resolve_target(target):
    devices = json.loads(Path(__file__).with_name('devices.json').read_text())
    if target in devices:
        return devices[target]['ip'], devices[target]
    for device in devices.values():
        if device['ip'] == target:
            return target, device
    return target, None


def verify_identity(lan, address, device):
    if device is None:
        raise ValueError('Control requires an identified bulb in devices.json; status remains read-only for other IPs')
    discoveries = LANScanner(lan).discover(timeout=3, address=address)
    match = next((d for d in discoveries if d['ipaddr'] == address), None)
    if not match:
        raise ValueError('Cannot verify the bulb identity through direct read-only UDP discovery')
    if match['id'].upper() != device['discovery_id'].upper():
        raise ValueError(f'IP identity changed: expected {device["discovery_id"]}, found {match["id"]}; rerun discovery')


def apply(bulb, args):
    check_control_support(bulb)
    if args.command == 'brightness' and bulb.mode not in {MODE_COLOR, MODE_WW}:
        raise ValueError('Brightness preservation requires a static RGB or white state')
    if args.command == 'brightness' and bulb.brightness == 0 and args.percent > 0:
        raise ValueError('Current channels are zero; choose an explicit RGB color or white temperature')
    if args.command == 'white' and not bulb.min_temp <= args.kelvin <= bulb.max_temp:
        raise ValueError(f'White temperature must be {bulb.min_temp}–{bulb.max_temp} K')
    # Initial state validation and capability checks always precede write access.
    bulb.writable = True
    try:
        if args.command == 'on':
            bulb.turnOn(retry=0)
        elif args.command == 'off':
            bulb.turnOff(retry=0)
        elif args.command == 'rgb':
            bulb.setRgb(args.red, args.green, args.blue, retry=0)
        elif args.command == 'white':
            level = round(args.brightness * 255 / 100)
            bulb.setWhiteTemperature(args.kelvin, level, retry=0)
        elif args.command == 'brightness':
            level = round(args.percent * 255 / 100)
            if bulb.color_mode == COLOR_MODE_CCT:
                bulb.setWhiteTemperature(bulb.color_temp, level, retry=0)
            elif bulb.color_mode == COLOR_MODE_RGB:
                bulb.setRgb(*bulb.rgb_unscaled, brightness=level, retry=0)
            else:
                raise ValueError('Cannot preserve this color mode while changing brightness')
    finally:
        bulb.writable = False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host', help='Bulb alias (tripod/reading) or IPv4 address on the active LAN')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('status', help='Read-only state query')
    sub.add_parser('on')
    sub.add_parser('off')
    brightness = sub.add_parser('brightness', help='Percent, preserving static RGB hue or white temperature')
    brightness.add_argument('percent', type=bounded_int(0, 100))
    rgb = sub.add_parser('rgb', help='RGB channels 0–255 (channel intensity determines brightness)')
    for channel in ['red', 'green', 'blue']:
        rgb.add_argument(channel, type=bounded_int(0, 255))
    white = sub.add_parser('white', help='White temperature using the library’s nominal calibration')
    white.add_argument('kelvin', type=bounded_int(2700, 6500))
    white.add_argument('--brightness', type=bounded_int(0, 100), default=50)
    args = parser.parse_args()
    bulb = None
    try:
        address, device = resolve_target(args.host)
        lan = active_lan()
        bulb = LANBulb(lan, address)
        if args.command != 'status':
            verify_identity(lan, address, device)
            apply(bulb, args)
            bulb.close()
            time.sleep(0.3)
            # A new object avoids optimistic channel values retained by the
            # library during the transition; report a fresh observed state.
            bulb = LANBulb(lan, address)
        state = snapshot(bulb)
        if device:
            state['name'] = device['name']
        print(json.dumps(state, indent=2))
    except Exception as exc:
        print(f'Error: {exc}', file=sys.stderr)
        if bulb and any(frame != '818a8b96' for frame in bulb.frames_sent):
            print('A write may have reached the bulb if read-back failed. Check status before retrying.', file=sys.stderr)
        return 1
    finally:
        if bulb:
            bulb.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
