"""
google_auth.py — Google OAuth 2.0 Login
=========================================
Handles Google login flow using requests library only.
No extra OAuth libraries needed.
"""

import os
import json
import secrets
import requests
from flask import Blueprint, redirect, request, session, url_for
from database import get_user_by_email, create_user, get_user_by_id

# ── Blueprint ─────────────────────────────────────────────────
google_auth = Blueprint('google_auth', __name__)

# ── Google OAuth endpoints ────────────────────────────────────
GOOGLE_AUTH_URL     = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL    = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

# ── Read credentials from environment ─────────────────────────
def get_google_creds():
    client_id     = os.environ.get('GOOGLE_CLIENT_ID', '')
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET', '')
    return client_id, client_secret


@google_auth.route('/auth/google')
def google_login():
    """Redirect user to Google login page."""
    client_id, _ = get_google_creds()

    if not client_id:
        return redirect(url_for('login') + '?error=Google+login+not+configured')

    # Generate state token to prevent CSRF
    state = secrets.token_hex(16)
    session['oauth_state'] = state

    # Build Google auth URL
    params = {
        'client_id':     client_id,
        'redirect_uri':  url_for('google_auth.google_callback', _external=True),
        'response_type': 'code',
        'scope':         'openid email profile',
        'state':         state,
        'access_type':   'online',
    }

    auth_url = GOOGLE_AUTH_URL + '?' + '&'.join(
        f"{k}={v}" for k, v in params.items()
    )
    return redirect(auth_url)


@google_auth.route('/auth/google/callback')
def google_callback():
    """Handle Google's redirect back to our app."""
    client_id, client_secret = get_google_creds()

    # Check for errors from Google
    error = request.args.get('error')
    if error:
        return redirect(url_for('login') + '?error=Google+login+cancelled')

    # Verify state to prevent CSRF
    state = request.args.get('state')
    if state != session.get('oauth_state'):
        return redirect(url_for('login') + '?error=Invalid+state')

    # Exchange auth code for access token
    code = request.args.get('code')
    token_data = {
        'code':          code,
        'client_id':     client_id,
        'client_secret': client_secret,
        'redirect_uri':  url_for('google_auth.google_callback', _external=True),
        'grant_type':    'authorization_code',
    }

    try:
        token_response = requests.post(GOOGLE_TOKEN_URL, data=token_data, timeout=10)
        token_json = token_response.json()
        access_token = token_json.get('access_token')

        if not access_token:
            return redirect(url_for('login') + '?error=Could+not+get+access+token')

        # Get user info from Google
        headers = {'Authorization': f'Bearer {access_token}'}
        user_info = requests.get(GOOGLE_USERINFO_URL, headers=headers, timeout=10).json()

        email = user_info.get('email')
        name  = user_info.get('name', email.split('@')[0] if email else 'User')

        if not email:
            return redirect(url_for('login') + '?error=Could+not+get+email+from+Google')

        # Check if user already exists
        user = get_user_by_email(email)

        if not user:
            # Create new user with random password (they log in via Google)
            random_password = secrets.token_hex(32)
            result = create_user(name, email, random_password)
            if not result['success']:
                return redirect(url_for('login') + '?error=Could+not+create+account')
            user = get_user_by_email(email)

        # Log user in
        session['user_id']   = user['id']
        session['user_name'] = user['name']
        return redirect(url_for('dashboard'))

    except requests.RequestException:
        return redirect(url_for('login') + '?error=Network+error+with+Google')
    except Exception as e:
        return redirect(url_for('login') + '?error=Login+failed')
