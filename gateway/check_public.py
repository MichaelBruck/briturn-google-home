"""Operator-approved, read-only end-to-end OAuth/QUERY check through public HTTPS.

Run on the TV box. Secrets stay in memory and its private directory. Does not
follow redirects to Google, link an account, or execute physical commands.
"""
from datetime import datetime, timezone
import hashlib
import http.cookiejar
import json
from pathlib import Path
import re
import secrets
import sqlite3
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    private = Path.home() / '.smart-bulb-bridge/gateway-private'
    config = json.loads((private / 'config.json').read_text())
    origin = config['public_url']
    assert re.fullmatch(r'https://[a-z0-9-]+\.trycloudflare\.com', origin)
    assert config['google_project_id'] == 'my-lights-project'
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), NoRedirect())
    credentials = []

    def call(path, form=None, data=None, headers=None):
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            headers = dict(headers or {}, **{'Content-Type': 'application/x-www-form-urlencoded'})
        req = urllib.request.Request(origin + path, data=data, headers=headers or {})
        try:
            response = opener.open(req, timeout=20)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.code, dict(response.headers), response.read().decode()

    report = {'time_utc': datetime.now(timezone.utc).isoformat(), 'public_url': origin,
              'live_writes': False, 'google_account_linked_by_this_check': False}
    try:
        status, _, body = call('/healthz')
        assert status == 200 and json.loads(body)['account_linking_configured']
        report['https_health'] = status
        status, _, _ = call('/fulfillment', data=b'{}', headers={'Content-Type': 'application/json'})
        assert status == 401
        report['unauthenticated_fulfillment'] = status
        redirect = 'https://oauth-redirect.googleusercontent.com/r/my-lights-project'
        state = secrets.token_urlsafe(24)
        params = dict(client_id=config['client_id'], response_type='code', scope='control',
                      redirect_uri=redirect, state=state)
        bad = dict(params, redirect_uri='https://unapproved.invalid/callback')
        status, headers, _ = call('/oauth/authorize?' + urllib.parse.urlencode(bad))
        assert status == 400 and 'Location' not in headers
        report['unapproved_redirect'] = status
        auth = '/oauth/authorize?' + urllib.parse.urlencode(params)
        status, _, html = call(auth)
        assert status == 200
        csrf = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)[1]
        status, _, _ = call(auth, form={'password': 'deliberately-invalid-fixture'})
        assert status == 400
        report['missing_csrf'] = status
        password = (private / 'gateway-password.txt').read_text().strip()
        status, headers, _ = call(auth, form={'csrf_token': csrf, 'password': password})
        assert status == 302
        target = urllib.parse.urlsplit(headers['Location'])
        assert urllib.parse.urlunsplit((target.scheme, target.netloc, target.path, '', '')) == redirect
        query = urllib.parse.parse_qs(target.query)
        assert query['state'] == [state]
        code = query['code'][0]
        credentials.append(code)
        exchange = dict(client_id=config['client_id'], client_secret=config['client_secret'],
                        grant_type='authorization_code', code=code, redirect_uri=redirect)
        status, _, _ = call('/oauth/token', form=dict(exchange, client_secret='deliberately-invalid-fixture'))
        assert status in (400, 401)
        report['wrong_client_secret'] = status
        status, _, body = call('/oauth/token', form=exchange)
        assert status == 200
        tokens = json.loads(body)
        credentials.extend([tokens['access_token'], tokens['refresh_token']])
        report['authorization_code_exchange'] = status
        status, _, _ = call('/oauth/token', form=exchange)
        assert status == 400
        report['replayed_code'] = status

        def intent(name, payload=None):
            message = {'requestId': 'public-read-only-check', 'inputs': [{
                'intent': 'action.devices.' + name, 'payload': payload or {}}]}
            status, _, body = call('/fulfillment', data=json.dumps(message).encode(), headers={
                'Content-Type': 'application/json', 'Authorization': 'Bearer ' + tokens['access_token']})
            assert status == 200
            return json.loads(body)

        sync = intent('SYNC')
        assert {d['id'] for d in sync['payload']['devices']} == {'tripod', 'reading'}
        report['sync'] = sync
        query_result = intent('QUERY', {'devices': [{'id': key} for key in ('tripod', 'reading')]})
        assert all(s['online'] for s in query_result['payload']['devices'].values())
        report['query'] = query_result
        refresh = dict(client_id=config['client_id'], client_secret=config['client_secret'],
                       grant_type='refresh_token', refresh_token=tokens['refresh_token'])
        status, _, body = call('/oauth/token', form=refresh)
        assert status == 200
        renewed = json.loads(body)
        credentials.extend([renewed['access_token'], renewed['refresh_token']])
        assert renewed['refresh_token'] != tokens['refresh_token']
        report['refresh_exchange'] = status
        status, _, _ = call('/oauth/token', form=refresh)
        assert status == 400
        report['replayed_refresh'] = status
    finally:
        # Remove only this check's credentials, preserving any later Google link.
        with sqlite3.connect(private / 'oauth.sqlite') as db:
            db.executemany('DELETE FROM credentials WHERE hash=?',
                [(hashlib.sha256(value.encode()).hexdigest(),) for value in credentials])
    status, _, _ = call('/fulfillment', data=b'{}', headers={
        'Content-Type': 'application/json', 'Authorization': 'Bearer ' + tokens['access_token']})
    assert status == 401
    report['cleaned_up_test_token'] = status
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
