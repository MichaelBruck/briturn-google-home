"""Portable flux_led adapter, limited to the two previously identified bulbs."""
import ipaddress
import socket
import threading
import time

from flux_led import BulbScanner, WifiLedBulb
from flux_led.const import COLOR_MODE_CCT, COLOR_MODE_RGB, MODE_COLOR, MODE_WW
from flux_led.protocol import ProtocolLEDENET8Byte


class ScopedBulb(WifiLedBulb):
    def __init__(self, source, host):
        self.source = source
        self.writable = False
        self.state_hex = None
        try:
            super().__init__(host, timeout=1.5)
        except Exception:
            if hasattr(self, '_socket'):
                self.close()
            raise

    def connect(self, retry=None):
        self.close()
        self._socket = socket.create_connection((self.ipaddr, self.port),
            timeout=self.timeout, source_address=(self.source, 0))

    def _protocol_probes(self):
        return (ProtocolLEDENET8Byte,)

    def _send_msg(self, msg):
        if not self.writable and bytes(msg) != bytes.fromhex('818a8b96'):
            raise ValueError('Read-only connection refused a write')
        self._socket.sendall(msg)

    def process_state_response(self, msg):
        if not ProtocolLEDENET8Byte().is_valid_state_response(msg) or msg[2] not in (0x23, 0x24):
            raise ValueError('Invalid standard state framing or checksum')
        self.state_hex = bytes(msg).hex()
        return super().process_state_response(msg)


class DirectScanner(BulbScanner):
    def __init__(self, source, host):
        super().__init__()
        self.source, self.host, self.sock = source, host, None

    def _create_socket(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.source, self.DISCOVERY_PORT))
        self.sock.setblocking(False)
        return self.sock

    def _process_response(self, data, from_address, address, response_list):
        if from_address[0] != self.host:
            return False
        try:
            done = super()._process_response(data, from_address, address, response_list)
            return done and bool(response_list.get(self.host, {}).get('id'))
        except (ValueError, UnicodeError, AssertionError):
            return False

    def identity(self):
        try:
            return next((d for d in self.scan(timeout=3, address=self.host)
                         if d['ipaddr'] == self.host and d.get('id')), None)
        finally:
            if self.sock:
                self.sock.close()


def validate_bulb(bulb):
    if (bulb.model_num != 0x35 or bulb.protocol != 'LEDENET_25_BYTE'
            or not {COLOR_MODE_CCT, COLOR_MODE_RGB}.issubset(bulb.color_modes)):
        raise ValueError('Device no longer matches the verified 0x35 RGBCW protocol')


def state(bulb):
    validate_bulb(bulb)
    result = {'online': True, 'on': bulb.is_on,
              'brightness': round(bulb.brightness * 100 / 255)}
    if bulb.color_mode == COLOR_MODE_CCT:
        result['color'] = {'temperatureK': bulb.color_temp}
    elif bulb.color_mode == COLOR_MODE_RGB:
        r, g, b = bulb.rgb_unscaled
        result['color'] = {'spectrumRgb': (r << 16) | (g << 8) | b}
    else:
        raise ValueError('Only static RGB and white modes are supported')
    return result


class Bulbs:
    def __init__(self, config):
        self.devices = config['devices']
        self.source = config['source_ip']
        self.writes_enabled = config.get('writes_enabled', False)
        self.lock = threading.RLock()
        network = ipaddress.ip_network(config['subnet'])
        if not network.is_private or network.prefixlen < 24:
            raise ValueError('Only the directly connected small private LAN is permitted')
        if ipaddress.ip_address(self.source) not in network:
            raise ValueError('Source is outside the configured LAN')
        for device in self.devices.values():
            ip = ipaddress.ip_address(device['ip'])
            if ip not in network or ip in (network.network_address, network.broadcast_address,
                                           ipaddress.ip_address(self.source)):
                raise ValueError('Bulb is outside the configured LAN')

    def read(self, device_id):
        with self.lock:
            bulb = ScopedBulb(self.source, self.devices[device_id]['ip'])
            try:
                return state(bulb)
            finally:
                bulb.close()

    def execute(self, device_id, operations):
        if not self.writes_enabled:
            raise PermissionError('Live writes have not been enabled')
        with self.lock:
            device = self.devices[device_id]
            identity = DirectScanner(self.source, device['ip']).identity()
            if not identity or identity['id'].upper() != device['discovery_id'].upper():
                raise ValueError('Cannot confirm the expected device identity')
            bulb = ScopedBulb(self.source, device['ip'])
            try:
                validate_bulb(bulb)
                if bulb.mode not in (MODE_COLOR, MODE_WW):
                    raise ValueError('A static color or white mode is required')
                bulb.writable = True
                for kind, value in operations:
                    if kind == 'on':
                        (bulb.turnOn if value else bulb.turnOff)(retry=0)
                    elif kind == 'brightness':
                        if value == 0:
                            bulb.turnOff(retry=0)
                        else:
                            level = round(value * 255 / 100)
                            if bulb.color_mode == COLOR_MODE_CCT:
                                bulb.setWhiteTemperature(bulb.color_temp, level, retry=0)
                            else:
                                bulb.setRgb(*bulb.rgb_unscaled, brightness=level, retry=0)
                            bulb.turnOn(retry=0)
                    elif kind == 'temperature':
                        bulb.setWhiteTemperature(value, bulb.brightness or 255, retry=0)
                        bulb.turnOn(retry=0)
                    elif kind == 'rgb':
                        if value == 0:
                            bulb.turnOff(retry=0)
                        else:
                            rgb = ((value >> 16) & 255, (value >> 8) & 255, value & 255)
                            bulb.setRgb(*rgb, brightness=bulb.brightness or 255, retry=0)
                            bulb.turnOn(retry=0)
                    # Refresh from hardware between batched operations; never use
                    # flux_led's optimistic retained channel values.
                    bulb.writable = False
                    bulb.close()
                    time.sleep(0.15)
                    bulb = ScopedBulb(self.source, device['ip'])
                    validate_bulb(bulb)
                    bulb.writable = True
                return state(bulb)
            finally:
                bulb.writable = False
                bulb.close()
