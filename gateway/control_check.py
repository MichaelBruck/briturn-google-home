"""Explicit live Reading Lamp test with exact channel/power restoration in finally."""
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from gateway.app import load_config
from gateway.bulbs import Bulbs, DirectScanner, ScopedBulb, state, validate_bulb


def main():
    config = load_config(Path.home() / '.smart-bulb-bridge/gateway-private/config.json')
    config['writes_enabled'] = True  # In this process only.
    backend = Bulbs(config)
    key = 'reading'
    device = backend.devices[key]
    original = ScopedBulb(backend.source, device['ip'])
    try:
        before = state(original)
        channels = (*original.rgb, original.raw_state.warm_white, original.raw_state.cool_white)
        before_hex = original.state_hex
    finally:
        original.close()
    report = {'time_utc': datetime.now(timezone.utc).isoformat(), 'device': key,
              'before': before, 'before_hex': before_hex, 'steps': []}
    try:
        for operation in [('brightness', 35), ('rgb', 255), ('on', False),
                          ('on', True), ('temperature', 3000)]:
            actual = backend.execute(key, [operation])
            report['steps'].append({'operation': operation, 'observed': actual})
            kind, value = operation
            if kind == 'brightness':
                assert abs(actual['brightness'] - value) <= 1, actual
            elif kind == 'rgb':
                assert actual['color'] == {'spectrumRgb': value}, actual
            elif kind == 'on':
                assert actual['on'] == value, actual
            elif kind == 'temperature':
                assert abs(actual['color']['temperatureK'] - value) < 50, actual
        report['control_test'] = 'passed'
    except Exception as exc:
        report['control_test'] = 'failed'
        report['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        identity = DirectScanner(backend.source, device['ip']).identity()
        if not identity or identity['id'].upper() != device['discovery_id'].upper():
            raise RuntimeError('Restore refused: expected bulb identity could not be verified')
        bulb = ScopedBulb(backend.source, device['ip'])
        try:
            validate_bulb(bulb)
            bulb.writable = True
            if 'temperatureK' in before['color']:
                bulb.set_levels(None, None, None, channels[3], channels[4], retry=0)
            else:
                bulb.set_levels(*channels[:3], None, None, retry=0)
            (bulb.turnOn if before['on'] else bulb.turnOff)(retry=0)
        finally:
            bulb.writable = False
            bulb.close()
        time.sleep(0.3)
        report['restored'] = backend.read(key)
        report['tripod_after'] = backend.read('tripod')
        report['restoration_matches'] = report['restored'] == before
        print(json.dumps(report, indent=2))
    if report.get('control_test') != 'passed' or not report['restoration_matches']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
