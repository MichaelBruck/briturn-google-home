"""Offline safety and framing tests; never sends to physical bulbs."""
import argparse
import ipaddress
import socket
import threading
import unittest
from unittest.mock import patch

from flux_led.protocol import ProtocolLEDENET8Byte
from controller import apply, check_control_support, verify_identity, resolve_target
from lan import LAN, LANBulb, snapshot


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.lan = LAN('en0', '192.168.3.120', ipaddress.IPv4Network('192.168.3.0/24'))
        # A synthesized standard reply, not an observation from a real device.
        self.state = ProtocolLEDENET8Byte().construct_message(
            bytearray([0x81, 0x35, 0x23, 0x61, 0x01, 0x01, 0, 0, 0, 128, 7, 64, 0x0F])
        )

    def bulb(self, frame=None):
        # Suppress I/O during construction; still execute real library parsing.
        with patch.object(LANBulb, 'setup', lambda self: None):
            bulb = LANBulb(self.lan, '192.168.3.50')
        bulb._set_protocol_from_msg(frame or self.state, 'LEDENET')
        bulb.process_state_response(frame or self.state)
        return bulb

    def test_lan_scope_rejects_non_hosts(self):
        for host in ['8.8.8.8', '192.168.4.2', '192.168.3.0', '192.168.3.255', '192.168.3.120', 'localhost']:
            with self.subTest(host=host), self.assertRaises(ValueError):
                self.lan.check_host(host)

    def test_bad_checksum_and_truncated_state_rejected(self):
        bulb = self.bulb()
        corrupted = self.state.copy()
        corrupted[-1] ^= 1
        for frame in [corrupted, self.state[:-1]]:
            with self.assertRaises(ValueError):
                bulb.process_state_response(frame)

    def test_read_only_refuses_light_change(self):
        bulb = self.bulb()
        with self.assertRaises(RuntimeError):
            bulb._send_msg(bytearray.fromhex('71230fa3'))
        self.assertEqual(bulb.frames_sent, [])

    def test_unknown_model_cannot_control(self):
        frame = self.state.copy()
        frame[1] = 0x44
        frame[-1] = sum(frame[:-1]) & 255
        bulb = self.bulb(frame)
        with self.assertRaises(ValueError):
            check_control_support(bulb)
        self.assertFalse(bulb.writable)

    def test_white_uses_library_framing(self):
        bulb = self.bulb()
        emitted = []
        with patch.object(bulb, '_process_levels_change', side_effect=lambda msgs, updates, **kw: emitted.extend(msgs)):
            apply(bulb, argparse.Namespace(command='white', kelvin=4000, brightness=50))
        self.assertEqual(len(emitted[0]), 9)
        self.assertEqual(emitted[0][6:8], bytes([0x0F, 0x0F]))
        self.assertEqual(emitted[0][-1], sum(emitted[0][:-1]) & 255)
        self.assertFalse(bulb.writable)

    def test_white_temperature_snapshot_is_present(self):
        self.assertIsInstance(snapshot(self.bulb())['white_temperature_kelvin_estimate'], int)

    def test_observed_version_ten_uses_25_byte_library_frame(self):
        # An observed read-only reply from the Tripod lamp. No writes to it.
        bulb = self.bulb(bytearray.fromhex('813523613050000000e90a0b0fc7'))
        self.assertEqual(bulb.protocol, 'LEDENET_25_BYTE')
        emitted = []
        with patch.object(bulb, '_process_levels_change', side_effect=lambda msgs, updates, **kw: emitted.extend(msgs)):
            apply(bulb, argparse.Namespace(command='white', kelvin=4000, brightness=50))
            apply(bulb, argparse.Namespace(command='rgb', red=255, green=0, blue=0))
        white, rgb = emitted
        self.assertEqual(len(white), 25)
        self.assertEqual(white[:4], bytes.fromhex('b0b1b2b3'))
        self.assertEqual(white[6], 2)  # Wrapper version
        self.assertEqual(white[8:10], bytes([0, 14]))  # Payload length
        self.assertEqual(white[13], 0xB1)  # White-only mask
        self.assertEqual(white[17:19], bytes([34, 50]))  # Nominal temp %, intensity %
        self.assertEqual(rgb[13], 0xA1)  # Color-only mask
        self.assertEqual(rgb[14:17], bytes([0, 100, 100]))  # Red HSV
        for frame in emitted:
            self.assertEqual(frame[-1], sum(frame[:-1]) & 255)
        self.assertFalse(bulb.writable)

    def test_alias_resolution_and_stale_ip_guard(self):
        address, device = resolve_target('tripod')
        self.assertEqual(address, '192.168.1.172')
        with patch('controller.LANScanner.discover', return_value=[{'ipaddr':address,'id':'0865F0AAAAAA'}]):
            verify_identity(self.lan, address, device)
        with patch('controller.LANScanner.discover', return_value=[{'ipaddr':address,'id':'0865F0BBBBBB'}]):
            with self.assertRaises(ValueError):
                verify_identity(self.lan, address, device)
        with self.assertRaises(ValueError):
            verify_identity(self.lan, '192.168.1.99', None)

    def test_fragmented_tcp_reply_and_exact_read_only_query(self):
        errors = []
        with socket.socket() as server:
            server.bind(('127.0.0.1', 0))
            server.listen()
            port = server.getsockname()[1]
            def respond():
                try:
                    with server.accept()[0] as conn:
                        query = b''
                        while len(query) < 4:
                            query += conn.recv(4 - len(query))
                        self.assertEqual(query, bytes.fromhex('818a8b96'))
                        conn.sendall(self.state[:2])
                        conn.sendall(self.state[2:9])
                        conn.sendall(self.state[9:])
                except BaseException as exc:
                    errors.append(exc)
            worker = threading.Thread(target=respond, daemon=True)
            worker.start()
            def connect_local(bulb, retry=None):
                bulb.close()
                bulb._socket = socket.create_connection(('127.0.0.1', port), timeout=2)
            with patch.object(LANBulb, 'connect', connect_local):
                bulb = LANBulb(self.lan, '192.168.3.50')
                try:
                    self.assertEqual(snapshot(bulb)['model_id'], '0x35')
                    self.assertEqual(bulb.frames_sent, ['818a8b96'])
                finally:
                    bulb.close()
            worker.join(timeout=3)
            self.assertFalse(worker.is_alive())
            if errors:
                raise errors[0]


if __name__ == '__main__':
    unittest.main()
