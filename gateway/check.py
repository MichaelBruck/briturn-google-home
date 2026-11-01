"""Self-check on the TV box: temporary OAuth fixture, real read-only bulb queries."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import parse_qs, urlencode, urlsplit

from werkzeug.security import generate_password_hash

from gateway.app import create_app, load_config
from gateway.bulbs import Bulbs


def main():
    config = load_config(Path.home() / '.smart-bulb-bridge/gateway-private/config.json')
    # All authentication here is disposable test data, separate from production
    # credentials. No request leaves the process or reaches Google.
    config.update(public_url='https://gateway-self-check.invalid', google_project_id='local-self-check',
                  client_id='fixture-client', client_secret='fixture-secret',
                  owner_id='local-fixture', session_secret='fixture-session-' * 4,
                  owner_password_hash=generate_password_hash('fixture-password', method='pbkdf2:sha256:1000'),
                  writes_enabled=False)
    backend = Bulbs(config)
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(config, backend, Path(tmp) / 'fixture.sqlite')
        client = app.test_client()
        base = {'base_url': config['public_url']}
        redirect = 'https://oauth-redirect.googleusercontent.com/r/local-self-check'
        auth = '/oauth/authorize?' + urlencode(dict(client_id='fixture-client',
            response_type='code', redirect_uri=redirect, state='self-check-state'))
        get = client.get(auth, **base)
        assert get.status_code == 200, get.status_code
        csrf = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', get.text)[1]
        post = client.post(auth, data={'csrf_token': csrf, 'password': 'fixture-password'}, **base)
        assert post.status_code == 302, post.status_code
        code = parse_qs(urlsplit(post.location).query)['code'][0]
        tokens = client.post('/oauth/token', data=dict(client_id='fixture-client',
            client_secret='fixture-secret', grant_type='authorization_code',
            code=code, redirect_uri=redirect), **base)
        assert tokens.status_code == 200, tokens.status_code
        headers = {'Authorization': 'Bearer ' + tokens.json['access_token']}
        def intent(name, payload=None):
            response = client.post('/fulfillment', headers=headers, json={
                'requestId': 'local-check', 'inputs': [{'intent': 'action.devices.' + name,
                                                       'payload': payload or {}}]}, **base)
            assert response.status_code == 200, response.status_code
            return response.json
        sync = intent('SYNC')
        query = intent('QUERY', {'devices': [{'id': key} for key in backend.devices]})
        assert all(v.get('online') for v in query['payload']['devices'].values()), query
        unauthorized = client.post('/fulfillment', json={}, **base)
        assert unauthorized.status_code == 401
        intent('DISCONNECT')
        revoked = client.post('/fulfillment', headers=headers, json={}, **base)
        assert revoked.status_code == 401
        print(json.dumps({'time_utc': datetime.now(timezone.utc).isoformat(),
            'mode': 'temporary-local-authentication-fixture', 'live_writes': False,
            'oauth_code_exchange': 'passed', 'unauthenticated_request': unauthorized.status_code,
            'revoked_token_request': revoked.status_code,
            'sync': sync, 'query': query}, indent=2))
        app.extensions['gateway_store'].db.close()


if __name__ == '__main__':
    main()
