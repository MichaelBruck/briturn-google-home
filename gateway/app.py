"""Loopback-only WSGI gateway. Public transport is a separate deployment step."""
import json
from pathlib import Path
import secrets
from urllib.parse import urlencode, urlsplit

from flask import Flask, Response, abort, jsonify, render_template_string, request
from flask_wtf import FlaskForm
from oauthlib.oauth2 import OAuth2Error, WebApplicationServer
from werkzeug.security import check_password_hash
from wtforms import PasswordField, SubmitField
from wtforms.validators import DataRequired, Length

from gateway.bulbs import Bulbs
from gateway.fulfillment import handle
from gateway.oauth_store import Store

PAGE = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>My Lights — link to Google</title>
<style>body{font:18px system-ui;max-width:32rem;margin:3rem auto;padding:0 1rem}
input,button{font:inherit;padding:.6rem;margin:.5rem 0}label{display:block}</style>
<h1>My Lights</h1>
<p>Link your private lighting gateway to Google.</p>
<p>Google will receive the names and current states of Tripod lamp and Reading Lamp,
and will be able to switch them, dim them and change their colour.</p>
<p>Enter your <strong>gateway password</strong>. Keep your Google password in Google's sign-in screen.</p>
{% if error %}<p role="alert">{{ error }}</p>{% endif %}
<form method="post">{{ form.hidden_tag() }}
{{ form.password.label }}{{ form.password(autocomplete="current-password",maxlength=256) }}
<p>By choosing Agree and link, you authorise Google to control these two lights.</p>
{{ form.link() }} <button name="cancel" value="1" formnovalidate>Cancel</button></form>
<p><a href="https://policies.google.com/privacy">Google Privacy Policy</a> ·
<a href="https://myaccount.google.com/connections">Manage linked accounts</a></p></html>'''


class LinkForm(FlaskForm):
    password = PasswordField('Gateway password', validators=[DataRequired(), Length(max=256)])
    link = SubmitField('Agree and link')


def create_app(config, backend=None, db_path=None):
    app = Flask(__name__)
    origin = config.get('public_url')
    parsed = urlsplit(origin or '')
    if origin and (parsed.scheme != 'https' or not parsed.hostname or parsed.username
                   or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        raise ValueError('public_url must be a canonical HTTPS origin')
    origin = origin.rstrip('/') if origin else None
    app.config.update(
        SECRET_KEY=config['session_secret'], MAX_CONTENT_LENGTH=32 * 1024,
        SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax', WTF_CSRF_TIME_LIMIT=600,
        TRUSTED_HOSTS=['localhost', '127.0.0.1'] + ([parsed.hostname] if origin else []),
    )
    backend = backend if backend is not None else Bulbs(config)
    store = Store(db_path or Path(config['private_dir']) / 'oauth.sqlite', config)
    oauth = WebApplicationServer(store, token_generator=lambda req: secrets.token_urlsafe(48),
                                 refresh_token_generator=lambda req: secrets.token_urlsafe(48),
                                 token_expires_in=3600)
    app.extensions.update(gateway_store=store, gateway_backend=backend)

    def uri():
        # Never infer the OAuth origin from untrusted forwarding headers.
        if not origin or not config.get('google_project_id'):
            abort(503, 'Google account linking has not been configured yet.')
        return origin + request.path + ('?' + request.query_string.decode('ascii')
                                        if request.query_string else '')

    def oauth_response(result):
        headers, body, status = result
        return Response(body, status=status, headers=headers)

    @app.after_request
    def headers(response):
        response.headers.update({
            'Cache-Control': 'no-store', 'Pragma': 'no-cache',
            'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
            'X-Frame-Options': 'DENY',
            'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; "
                                       "form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
        })
        return response

    @app.get('/healthz')
    def health():
        return jsonify(status='ok', account_linking_configured=bool(origin and config.get('google_project_id')))

    @app.route('/oauth/authorize', methods=['GET', 'POST'])
    def authorize():
        url = uri()
        # State must be present and echoed only to an exact Google redirect.
        if not request.args.get('state') or len(request.args['state']) > 2048:
            abort(400)
        try:
            with store.lock:
                scopes, credentials = oauth.validate_authorization_request(url, http_method='GET')
        except (OAuth2Error, ValueError, UnicodeError):
            abort(400, 'Invalid account-linking request.')
        form = LinkForm()
        error = None
        if request.method == 'POST':
            if not form.csrf_token.current_token or not form.csrf_token.data:
                abort(400)
            # Validate CSRF even for cancellation, which deliberately allows an empty password.
            if request.form.get('cancel'):
                if not form.csrf_token.validate(form):
                    abort(400)
                target = credentials['redirect_uri'] + '?' + urlencode({
                    'error': 'access_denied', 'state': credentials['state']})
                return Response(status=302, headers={'Location': target})
            if not form.validate_on_submit():
                abort(400, 'Invalid or expired form. Reopen account linking.')
            if not store.allow_password_attempt(request.remote_addr):
                abort(429, 'Too many attempts. Try again in 15 minutes.')
            if check_password_hash(config['owner_password_hash'], form.password.data):
                with store.lock:
                    return oauth_response(oauth.create_authorization_response(
                        url, http_method='GET', scopes=scopes,
                        credentials={'user': config['owner_id']}))
            error = 'The gateway password was not recognised.'
        return render_template_string(PAGE, form=form, error=error), (401 if error else 200)

    @app.post('/oauth/token')
    def token():
        if request.mimetype != 'application/x-www-form-urlencoded':
            abort(400)
        body = request.get_data(as_text=True)
        if any(len(request.form.getlist(key)) != 1 for key in request.form):
            abort(400)
        with store.lock:
            return oauth_response(oauth.create_token_response(
                uri(), http_method='POST', body=body,
                headers=dict(request.headers)))

    @app.post('/fulfillment')
    def fulfillment():
        # Only Authorization-header bearer tokens; never URL or body credentials.
        if request.query_string or not request.headers.get('Authorization', '').startswith('Bearer '):
            return Response(status=401, headers={'WWW-Authenticate': 'Bearer error="invalid_token"'})
        with store.lock:
            valid, _ = oauth.verify_request(uri(), http_method='POST',
                headers=dict(request.headers), scopes=['control'])
        if not valid:
            return Response(status=401, headers={'WWW-Authenticate': 'Bearer error="invalid_token"'})
        message = request.get_json()
        return jsonify(handle(message, backend, config['owner_id'], store.revoke_all))

    return app


def load_config(path):
    path = Path(path).resolve()
    if path.stat().st_mode & 0o077:
        raise ValueError('Gateway config must be readable only by its owner (chmod 600)')
    config = json.loads(path.read_text())
    config['private_dir'] = str(path.parent)
    return config
