"""OAuthLib validator for one owner and one explicitly configured Google client."""
import base64
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3
import threading
import time
from types import SimpleNamespace
from urllib.parse import unquote

from oauthlib.oauth2 import RequestValidator


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class Store(RequestValidator):
    def __init__(self, path, config):
        self.config = config
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        Path(path).chmod(0o600)
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS credentials (
                kind TEXT, hash TEXT, data TEXT, expires REAL,
                PRIMARY KEY(kind, hash));
            CREATE TABLE IF NOT EXISTS attempts (ip TEXT, stamp REAL);
            CREATE INDEX IF NOT EXISTS attempts_time ON attempts(stamp);
        ''')

    @property
    def client_id(self):
        return self.config['client_id']

    @property
    def redirects(self):
        project = self.config['google_project_id']
        return {f'https://{host}/r/{project}' for host in (
            'oauth-redirect.googleusercontent.com',
            'oauth-redirect-sandbox.googleusercontent.com')}

    def put(self, kind, value, data, ttl=None):
        now = time.time()
        with self.lock, self.db:
            self.db.execute('DELETE FROM credentials WHERE expires < ?', (now,))
            self.db.execute('INSERT OR REPLACE INTO credentials VALUES (?,?,?,?)',
                            (kind, digest(value), json.dumps(data), now + ttl if ttl else None))

    def get(self, kind, value, consume=False):
        if not isinstance(value, str) or not value or len(value) > 1024:
            return None
        with self.lock, self.db:
            row = self.db.execute('SELECT * FROM credentials WHERE kind=? AND hash=?',
                                  (kind, digest(value))).fetchone()
            if not row or (row['expires'] is not None and row['expires'] < time.time()):
                return None
            if consume:
                self.db.execute('DELETE FROM credentials WHERE kind=? AND hash=?',
                                (kind, digest(value)))
            return json.loads(row['data'])

    def revoke_all(self):
        with self.lock, self.db:
            self.db.execute('DELETE FROM credentials')

    def allow_password_attempt(self, ip):
        # Durable global limit also works behind a loopback tunnel without
        # trusting user-supplied X-Forwarded-For headers.
        now = time.time()
        with self.lock, self.db:
            self.db.execute('DELETE FROM attempts WHERE stamp < ?', (now - 900,))
            count = self.db.execute('SELECT count(*) FROM attempts').fetchone()[0]
            if count >= 10:
                return False
            self.db.execute('INSERT INTO attempts VALUES (?,?)', (ip, now))
            return True

    def validate_client_id(self, client_id, request, *args, **kwargs):
        return bool(isinstance(client_id, str) and hmac.compare_digest(
            client_id.encode(), self.client_id.encode()))

    def validate_redirect_uri(self, client_id, redirect_uri, request, *args, **kwargs):
        return redirect_uri in self.redirects

    def get_default_redirect_uri(self, client_id, request, *args, **kwargs):
        return None  # An exact explicit redirect is mandatory.

    def validate_response_type(self, client_id, response_type, client, request, *args, **kwargs):
        return response_type == 'code'

    def get_default_scopes(self, client_id, request, *args, **kwargs):
        return ['control']

    def validate_scopes(self, client_id, scopes, client, request, *args, **kwargs):
        return scopes == ['control']

    def client_authentication_required(self, request, *args, **kwargs):
        return True

    def authenticate_client(self, request, *args, **kwargs):
        cid, secret = request.client_id, request.client_secret
        header = request.headers.get('Authorization', '')
        if header:
            if not header.startswith('Basic ') or cid or secret:
                return False
            try:
                decoded = base64.b64decode(header[6:], validate=True).decode()
                cid, secret = map(unquote, decoded.split(':', 1))
            except (ValueError, UnicodeError):
                return False
        if not (self.validate_client_id(cid, request) and isinstance(secret, str)
                and hmac.compare_digest(secret.encode(), self.config['client_secret'].encode())):
            return False
        request.client = SimpleNamespace(client_id=cid)
        request.client_id = cid
        return True

    def validate_grant_type(self, client_id, grant_type, client, request, *args, **kwargs):
        return grant_type in {'authorization_code', 'refresh_token'}

    def save_authorization_code(self, client_id, code, request, *args, **kwargs):
        self.put('code', code['code'], {
            'client_id': client_id, 'redirect_uri': request.redirect_uri,
            'user': request.user, 'scopes': request.scopes,
            'challenge': request.code_challenge, 'method': request.code_challenge_method,
        }, 300)

    def validate_code(self, client_id, code, client, request, *args, **kwargs):
        record = self.get('code', code, consume=True)
        if not record or record['client_id'] != client_id:
            return False
        request.user, request.scopes = record['user'], record['scopes']
        request.code_record = record
        return True

    def get_code_challenge(self, code, request):
        return request.code_record.get('challenge')

    def get_code_challenge_method(self, code, request):
        return request.code_record.get('method')

    def confirm_redirect_uri(self, client_id, code, redirect_uri, client, request, *args, **kwargs):
        return request.code_record['redirect_uri'] == redirect_uri

    def invalidate_authorization_code(self, client_id, code, request, *args, **kwargs):
        pass  # Already atomically consumed during validation, including failed exchanges.

    def save_bearer_token(self, token, request, *args, **kwargs):
        record = {'client_id': request.client_id, 'user': request.user,
                  'scopes': request.scopes}
        self.put('access', token['access_token'], record, token['expires_in'])
        if token.get('refresh_token'):
            self.put('refresh', token['refresh_token'], record)

    def validate_refresh_token(self, refresh_token, client, request, *args, **kwargs):
        record = self.get('refresh', refresh_token, consume=True)
        if not record or record['client_id'] != client.client_id:
            return False
        request.user, request.refresh_record = record['user'], record
        return True

    def get_original_scopes(self, refresh_token, request, *args, **kwargs):
        return request.refresh_record['scopes']

    def validate_bearer_token(self, token, scopes, request):
        record = self.get('access', token)
        if not record or record['client_id'] != self.client_id:
            return False
        if not set(scopes).issubset(record['scopes']):
            return False
        request.user, request.scopes = record['user'], record['scopes']
        return True
