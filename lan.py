"""Constrain the existing flux_led implementation to one physical Mac LAN."""
import ipaddress
import re
import socket
import subprocess
import sys
from dataclasses import dataclass

from flux_led import BulbScanner, WifiLedBulb
from flux_led.protocol import ProtocolLEDENET8Byte
from flux_led.const import COLOR_MODE_CCT


@dataclass(frozen=True)
class LAN:
    interface: str
    address: str
    subnet: ipaddress.IPv4Network

    def check_host(self, address):
        ip = ipaddress.IPv4Address(address)
        if ip not in self.subnet or ip in (
            self.subnet.network_address, self.subnet.broadcast_address,
            ipaddress.IPv4Address(self.address),
        ):
            raise ValueError(f"{address} is not a remote host on {self.subnet}")
        return str(ip)


def active_lan():
    route = subprocess.check_output(['/sbin/route', '-n', 'get', 'default'], text=True)
    match = re.search(r'interface:\s*(en\d+)\b', route)
    if not match:
        raise RuntimeError('Default route is not a physical en* LAN; refusing discovery')
    interface = match[1]
    config = subprocess.check_output(['/sbin/ifconfig', interface], text=True)
    match = re.search(r'inet (\d+\.\d+\.\d+\.\d+) netmask (0x[0-9a-f]+)', config)
    if not match or 'status: active' not in config:
        raise RuntimeError('Physical LAN has no active IPv4 address')
    address = match[1]
    mask = str(ipaddress.IPv4Address(int(match[2], 16)))
    subnet = ipaddress.IPv4Network(f'{address}/{mask}', strict=False)
    if not ipaddress.IPv4Address(address).is_private:
        raise RuntimeError('Refusing discovery on a public IPv4 network')
    return LAN(interface, address, subnet)


def bind_lan(sock, lan, port=0):
    if sys.platform != 'darwin':
        raise RuntimeError('This project currently scopes sockets for macOS only')
    # Darwin <netinet/in.h>: IP_BOUND_IF = 25. Excludes VPN/other interfaces.
    sock.setsockopt(socket.IPPROTO_IP, 25, socket.if_nametoindex(lan.interface))
    sock.bind((lan.address, port))


class LANScanner(BulbScanner):
    def __init__(self, lan):
        super().__init__()
        self.lan = lan
        self.socket = None
        self.replies = []

    def _create_socket(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            bind_lan(sock, self.lan, self.DISCOVERY_PORT)
        except OSError:
            sock.close()
            raise  # Do not silently change legacy discovery's source port.
        sock.setblocking(False)
        self.socket = sock
        return sock

    def _process_response(self, data, from_address, address, response_list):
        try:
            self.lan.check_host(from_address[0])
        except ValueError:
            return False
        self.replies.append({'source': from_address, 'hex': data.hex()})
        try:
            complete = super()._process_response(data, from_address, address, response_list)
            # Upstream can finish a unicast scan after version/cloud replies
            # before the actual identity reply arrives. Require that identity.
            return complete and bool(response_list.get(from_address[0], {}).get('id'))
        except (ValueError, UnicodeError, AssertionError):
            return False

    def discover(self, timeout=8, address=None):
        destination = address or str(self.lan.subnet.broadcast_address)
        if address:
            self.lan.check_host(address)
        try:
            found = self.scan(timeout=timeout, address=destination)
            return [d for d in found if self.lan.check_host(d['ipaddr'])]
        finally:
            if self.socket:
                self.socket.close()


class LANBulb(WifiLedBulb):
    def __init__(self, lan, address, discovery=None, writable=False):
        self.lan = lan
        self.writable = writable
        self.frames_sent = []
        self.state_frames = []
        try:
            super().__init__(lan.check_host(address), timeout=2, discovery=discovery)
        except Exception:
            if hasattr(self, '_socket'):
                self.close()
            raise

    def connect(self, retry=None):
        self.close()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket = sock
        sock.settimeout(self.timeout)
        bind_lan(sock, self.lan)
        sock.connect((self.ipaddr, self.port))

    def _protocol_probes(self):
        # Phase one only probes the verified checksum-based 2014 query.
        return (ProtocolLEDENET8Byte,)

    def _send_msg(self, msg):
        if not self.writable and bytes(msg) != b'\x81\x8a\x8b\x96':
            raise RuntimeError('Read-only connection refused a non-state-query frame')
        self.frames_sent.append(bytes(msg).hex())
        self._socket.sendall(msg)

    def process_state_response(self, msg):
        # Require standard 14-byte checksum validation even if a future protocol
        # parser is more permissive. Unknown framing is evidence, not identity.
        if not ProtocolLEDENET8Byte().is_valid_state_response(msg):
            raise ValueError(f'Invalid 2014 state response: {bytes(msg).hex()}')
        if msg[2] not in (0x23, 0x24):
            raise ValueError('Unknown power-state byte')
        self.state_frames.append(bytes(msg).hex())
        return super().process_state_response(msg)


def snapshot(bulb):
    return {
        'ip': bulb.ipaddr,
        'model': bulb.model,
        'model_id': f'0x{bulb.model_num:02X}',
        'version_byte': bulb.version_num,
        'protocol': bulb.protocol,
        'on': bulb.is_on,
        'mode': bulb.mode,
        'color_mode': bulb.color_mode,
        'supported_color_modes': sorted(bulb.color_modes),
        'brightness_percent': round(bulb.brightness * 100 / 255, 1),
        'rgb': list(bulb.rgb),
        'warm_white': bulb.raw_state.warm_white,
        'cool_white': bulb.raw_state.cool_white,
        'white_temperature_kelvin_estimate': bulb.color_temp if bulb.color_mode == COLOR_MODE_CCT else None,
        'library_temperature_range_kelvin': [bulb.min_temp, bulb.max_temp],
        'raw_state_hex': bulb.state_frames[-1],
    }
