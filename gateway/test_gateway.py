"""Offline integration tests: real OAuthLib/Flask/SQLite, simulated hardware only."""
from concurrent.futures import ThreadPoolExecutor
import base64
import hashlib
import json
from pathlib import Path
import re
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock
from urllib.parse import parse_qs, urlencode, urlsplit

from werkzeug.security import generate_password_hash

from gateway.app import create_app
from gateway.fulfillment import handle
from gateway.bulbs import Bulbs, ScopedBulb


class FakeBulbs:
    devices = {'tripod': {'name': 'Tripod lamp'}, 'reading': {'name': 'Reading Lamp'}}

    def __init__(self):
        self.writes = []

    def read(self, key):
        return {'online': True, 'on': True, 'brightness': 100,
                'color': {'temperatureK': 4000}}

    def execute(self, key, ops):
        self.writes.append((key, ops))
        return self.read(key)


class GatewayTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = dict(public_url='https://bridge.test', google_project_id='project-123',
            client_id='client', client_secret='secret', owner_id='owner',
            session_secret='a' * 64,
            owner_password_hash=generate_password_hash('gateway-password', method='pbkdf2:sha256:1000'))
        self.backend = FakeBulbs()
        self.app = create_app(self.config, self.backend, Path(self.temp.name) / 'tokens.sqlite')
        self.client = self.app.test_client()
        self.redirect = 'https://oauth-redirect.googleusercontent.com/r/project-123'
        self.auth = '/oauth/authorize?' + urlencode(dict(
            client_id='client', redirect_uri=self.redirect, response_type='code', state='opaque-state'))
        self.store = self.app.extensions['gateway_store']

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def get(self, path):
        return self.client.get(path, base_url='https://bridge.test')

    def post(self, path, **kwargs):
        return self.client.post(path, base_url='https://bridge.test', **kwargs)

    def code(self):
        response = self.get(self.auth)
        self.assertEqual(response.status_code, 200)
        csrf = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', response.text)[1]
        response = self.post(self.auth, data={'csrf_token': csrf, 'password': 'gateway-password'})
        self.assertEqual(response.status_code, 302, response.text)
        parsed = urlsplit(response.location)
        self.assertEqual(parsed.scheme + '://' + parsed.netloc + parsed.path, self.redirect)
        values = parse_qs(parsed.query)
        self.assertEqual(values['state'], ['opaque-state'])
        return values['code'][0]

    def exchange(self, code, **overrides):
        data = dict(client_id='client', client_secret='secret', grant_type='authorization_code',
                    code=code, redirect_uri=self.redirect)
        data.update(overrides)
        return self.post('/oauth/token', data=data)

    def issue(self):
        response = self.exchange(self.code())
        self.assertEqual(response.status_code, 200, response.text)
        return response.json

    def intent(self, token, intent, payload=None):
        return self.post('/fulfillment', headers={'Authorization': 'Bearer ' + token}, json={
            'requestId': 'request-1', 'inputs': [{'intent': 'action.devices.' + intent,
                                                'payload': payload or {}}]})

    def test_link_sync_query_execute_and_disconnect(self):
        token = self.issue()['access_token']
        sync = self.intent(token, 'SYNC').json
        self.assertEqual([d['id'] for d in sync['payload']['devices']], ['tripod', 'reading'])
        query = self.intent(token, 'QUERY', {'devices': [{'id': 'reading'}]}).json
        self.assertTrue(query['payload']['devices']['reading']['on'])
        execute = self.intent(token, 'EXECUTE', {'commands': [{
            'devices': [{'id': 'reading'}], 'execution': [{
                'command': 'action.devices.commands.BrightnessAbsolute', 'params': {'brightness': 40}}]}]}).json
        self.assertEqual(execute['payload']['commands'][0]['status'], 'SUCCESS')
        self.assertEqual(self.backend.writes, [('reading', [('brightness', 40)])])
        self.assertEqual(self.intent(token, 'DISCONNECT').json, {})
        self.assertEqual(self.intent(token, 'QUERY').status_code, 401)

    def test_bad_redirect_client_scope_state_and_duplicate(self):
        for suffix in [self.auth.replace('project-123', 'other-project'),
                       self.auth.replace('client_id=client', 'client_id=attacker'),
                       self.auth + '&scope=admin', self.auth + '&client_id=client',
                       self.auth.replace('opaque-state', '')]:
            response = self.get(suffix)
            self.assertEqual(response.status_code, 400)
            self.assertNotIn('Location', response.headers)

    def test_csrf_required_and_wrong_password(self):
        self.assertEqual(self.post(self.auth, data={'password': 'gateway-password'}).status_code, 400)
        response = self.get(self.auth)
        csrf = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', response.text)[1]
        self.assertEqual(self.post(self.auth, data={'password': 'wrong', 'csrf_token': csrf}).status_code, 401)
        self.assertEqual(self.post(self.auth, data={'cancel': '1', 'csrf_token': 'invalid'}).status_code, 400)
        response = self.post(self.auth, data={'cancel': '1', 'csrf_token': csrf})
        self.assertEqual(parse_qs(urlsplit(response.location).query)['error'], ['access_denied'])

    def test_code_one_use_expiry_redirect_and_client_secret(self):
        code = self.code()
        self.assertNotEqual(self.exchange(code, client_secret='wrong').status_code, 200)
        self.assertEqual(self.exchange(code).status_code, 200)
        self.assertNotEqual(self.exchange(code).status_code, 200)
        code = self.code()
        self.assertNotEqual(self.exchange(code, redirect_uri='https://evil.test').status_code, 200)
        self.assertNotEqual(self.exchange(code).status_code, 200)
        code = self.code()
        self.store.db.execute("UPDATE credentials SET expires=0 WHERE kind='code'")
        self.store.db.commit()
        self.assertNotEqual(self.exchange(code).status_code, 200)

    def test_concurrent_code_exchange_only_once(self):
        code = self.code()
        def exchange(_):
            with self.app.test_client() as client:
                return client.post('/oauth/token', base_url='https://bridge.test', data=dict(
                    client_id='client', client_secret='secret', grant_type='authorization_code',
                    code=code, redirect_uri=self.redirect)).status_code
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(exchange, range(2)))
        self.assertEqual(results.count(200), 1)

    def test_refresh_rotation_and_bearer_expiry(self):
        tokens = self.issue()
        data = dict(client_id='client', client_secret='secret', grant_type='refresh_token',
                    refresh_token=tokens['refresh_token'])
        refreshed = self.post('/oauth/token', data=data)
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        self.assertNotEqual(refreshed.json['refresh_token'], tokens['refresh_token'])
        self.assertNotEqual(self.post('/oauth/token', data=data).status_code, 200)
        self.store.db.execute("UPDATE credentials SET expires=0 WHERE kind='access'")
        self.store.db.commit()
        self.assertEqual(self.intent(tokens['access_token'], 'SYNC').status_code, 401)

    def test_basic_client_auth_and_pkce_verification(self):
        verifier = 'a-long-fixture-verifier-with-more-than-43-characters'
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        self.auth += '&' + urlencode({'code_challenge': challenge, 'code_challenge_method': 'S256'})
        code = self.code()
        data = dict(grant_type='authorization_code', code=code, redirect_uri=self.redirect,
                    code_verifier=verifier)
        basic = base64.b64encode(b'client:secret').decode()
        response = self.post('/oauth/token', data=data, headers={'Authorization': 'Basic ' + basic})
        self.assertEqual(response.status_code, 200, response.text)
        code = self.code()
        self.assertNotEqual(self.exchange(code, code_verifier='wrong-verifier').status_code, 200)

    def test_no_token_url_tokens_unknown_hosts_and_missing_configuration(self):
        self.assertEqual(self.post('/fulfillment', json={}).status_code, 401)
        token = self.issue()['access_token']
        self.assertEqual(self.post('/fulfillment?access_token=' + token, json={}).status_code, 401)
        self.assertEqual(self.client.get('/healthz', base_url='http://attacker.test').status_code, 400)
        config = dict(self.config, public_url=None, google_project_id=None)
        app = create_app(config, self.backend, Path(self.temp.name) / 'unconfigured.sqlite')
        self.assertEqual(app.test_client().get(self.auth).status_code, 503)
        app.extensions['gateway_store'].db.close()

    def test_tokens_not_stored_in_plaintext_and_security_headers(self):
        tokens = self.issue()
        stored = Path(self.temp.name, 'tokens.sqlite').read_bytes()
        self.assertNotIn(tokens['access_token'].encode(), stored)
        self.assertNotIn(tokens['refresh_token'].encode(), stored)
        response = self.get('/healthz')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['X-Frame-Options'], 'DENY')

    def test_invalid_batch_writes_nothing_and_color_spelling(self):
        token = self.issue()['access_token']
        prefix = 'action.devices.commands.'
        payload = {'commands': [{'devices': [{'id': 'reading'}], 'execution': [
            {'command': prefix + 'OnOff', 'params': {'on': False}},
            {'command': prefix + 'ColorAbsolute', 'params': {'color': {'temperature': 9000}}}]}]}
        self.assertEqual(self.intent(token, 'EXECUTE', payload).json['payload']['errorCode'], 'valueOutOfRange')
        self.assertEqual(self.backend.writes, [])
        payload['commands'][0]['execution'] = [{'command': prefix + 'ColorAbsolute',
                                               'params': {'color': {'spectrumRGB': 0xFF0080}}}]
        self.assertEqual(self.intent(token, 'EXECUTE', payload).json['payload']['commands'][0]['status'], 'SUCCESS')
        self.assertEqual(self.backend.writes[-1][1], [('rgb', 0xFF0080)])

    def test_offline_unknown_and_malformed_payloads(self):
        token = self.issue()['access_token']
        for value in [None, [], {}, {'requestId': 'a', 'inputs': [{'intent': 'action.devices.EXECUTE',
                    'payload': {'commands': [{'devices': [{'id': ['bad']}], 'execution': []}]}}]}]:
            result = handle(value, self.backend, 'owner', lambda: None)
            self.assertIn('errorCode', result['payload'])
        result = self.intent(token, 'QUERY', {'devices': [{'id': 'unknown'}]}).json
        self.assertEqual(result['payload']['devices']['unknown']['errorCode'], 'deviceNotFound')
        def offline(key):
            raise TimeoutError()
        self.backend.read = offline
        result = self.intent(token, 'QUERY', {'devices': [{'id': 'reading'}]}).json
        self.assertFalse(result['payload']['devices']['reading']['online'])
        self.assertEqual(self.backend.writes, [])


class HardwareGuardsTest(unittest.TestCase):
    def config(self):
        return dict(source_ip='192.168.1.199', subnet='192.168.1.0/24',
                    devices={'reading': {'ip': '192.168.1.195', 'discovery_id': '0865F0BBBBBB'}},
                    writes_enabled=True)

    def test_wrong_identity_never_connects_or_writes(self):
        with patch('gateway.bulbs.DirectScanner') as scanner, patch('gateway.bulbs.ScopedBulb') as bulb:
            scanner.return_value.identity.return_value = {'id': 'other-device'}
            with self.assertRaises(ValueError):
                Bulbs(self.config()).execute('reading', [('on', False)])
            bulb.assert_not_called()

    def test_disabled_writes_and_wrong_subnet_fail_closed(self):
        config = self.config()
        config['writes_enabled'] = False
        with self.assertRaises(PermissionError), patch('gateway.bulbs.DirectScanner') as scanner:
            Bulbs(config).execute('reading', [('on', False)])
        scanner.assert_not_called()
        config['source_ip'] = '192.168.3.199'
        with self.assertRaises(ValueError):
            Bulbs(config)

    def test_read_only_and_checksum_guards(self):
        bulb = ScopedBulb.__new__(ScopedBulb)
        bulb.writable = False
        bulb._socket = MagicMock()
        with self.assertRaises(ValueError):
            bulb._send_msg(bytes.fromhex('71230fa3'))
        bulb._socket.sendall.assert_not_called()
        bulb._send_msg(bytes.fromhex('818a8b96'))
        bulb._socket.sendall.assert_called_once_with(bytes.fromhex('818a8b96'))
        with self.assertRaises(ValueError):
            bulb.process_state_response(bytes.fromhex('813523613050000000a90a560fd3'))


if __name__ == '__main__':
    unittest.main()
