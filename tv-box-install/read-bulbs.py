"""Read-only known-bulb checks on the Android box, using flux_led framing."""
from datetime import datetime
import ipaddress
import json
import socket

from flux_led import WifiLedBulb
from flux_led.const import COLOR_MODE_CCT
from flux_led.protocol import ProtocolLEDENET8Byte

SOURCE = '192.168.1.199'
LAN = ipaddress.IPv4Network('192.168.1.0/24')
BULBS = {'tripod': '192.168.1.172', 'reading': '192.168.1.195'}


class ReadOnlyBulb(WifiLedBulb):
    def __init__(self, host):
        if ipaddress.IPv4Address(host) not in LAN or host not in BULBS.values():
            raise ValueError('Only the two identified bulbs are allowed')
        self.frames_sent = []
        self.state_hex = None
        try:
            super().__init__(host, timeout=3)
        except Exception:
            if hasattr(self, '_socket'):
                self.close()
            raise

    def connect(self, retry=None):
        self.close()
        self._socket = socket.create_connection(
            (self.ipaddr, self.port), timeout=self.timeout,
            source_address=(SOURCE, 0),
        )

    def _protocol_probes(self):
        return (ProtocolLEDENET8Byte,)

    def _send_msg(self, msg):
        if bytes(msg) != bytes.fromhex('818a8b96'):
            raise ValueError('Read-only probe refused a non-query frame')
        self.frames_sent.append(bytes(msg).hex())
        self._socket.sendall(msg)

    def process_state_response(self, msg):
        if not ProtocolLEDENET8Byte().is_valid_state_response(msg):
            raise ValueError('Invalid state framing or checksum')
        if msg[2] not in (0x23, 0x24):
            raise ValueError('Invalid power byte')
        self.state_hex = bytes(msg).hex()
        return super().process_state_response(msg)


def main():
    results = []
    for alias, ip in BULBS.items():
        bulb = None
        try:
            bulb = ReadOnlyBulb(ip)
            results.append({
                'alias': alias, 'ip': ip, 'model': bulb.model,
                'version_byte': bulb.version_num, 'protocol': bulb.protocol,
                'on': bulb.is_on, 'color_mode': bulb.color_mode,
                'brightness_percent': round(bulb.brightness * 100 / 255, 1),
                'temperature_kelvin_estimate': bulb.color_temp if bulb.color_mode == COLOR_MODE_CCT else None,
                'rgb': list(bulb.rgb), 'warm_white': bulb.raw_state.warm_white,
                'cool_white': bulb.raw_state.cool_white,
                'raw_state_hex': bulb.state_hex, 'sent_frames': bulb.frames_sent,
            })
        except Exception as exc:
            results.append({'alias': alias, 'ip': ip, 'error': str(exc)})
        finally:
            if bulb:
                bulb.close()
    print(json.dumps({'time': datetime.now().astimezone().isoformat(), 'source_ip': SOURCE,
                      'read_only': True, 'bulbs': results}, indent=2))


if __name__ == '__main__':
    main()
