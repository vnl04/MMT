#
# Copyright (C) 2026 pdnguyen of HCMC University of Technology VNU-HCM.
# All rights reserved.
# This file is part of the CO3093/CO3094 course,
# and is released under the "MIT License Agreement". Please see the LICENSE
# file that should have been included as part of this package.
#
# AsynapRous release
#
# The authors hereby grant to Licensee personal permission to use
# and modify the Licensed Source Code for the sole purpose of studying
# while attending the course
#


"""
app.sampleapp
~~~~~~~~~~~~~~~~~

Sample RESTful web application using AsynapRous framework.
Includes login with authentication, echo, and hello endpoints.
"""

import sys
import os
import json
import hashlib
import base64

from daemon import AsynapRous

app = AsynapRous()

# ------------------------------------------------------------------
# Simple user "database" stored as a dict {username: hashed_password}
# In real scenario this would come from db/ directory
# ------------------------------------------------------------------
def _hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

USER_DB = {
    "admin":  _hash_password("admin123"),
    "student": _hash_password("hcmut2026"),
    "guest":  _hash_password("guest"),
}

# Active sessions: {token: username}
SESSIONS = {}


def _make_token(username):
    raw = "{}:{}".format(username, os.urandom(8).hex())
    return base64.b64encode(raw.encode()).decode()


def _parse_body(body):
    """Try to parse body as JSON, fallback to url-encoded form."""
    try:
        return json.loads(body)
    except (json.JSONDecodeError, TypeError):
        pass
    # url-encoded: username=foo&password=bar
    params = {}
    if body:
        for pair in body.split('&'):
            pair = pair.strip()
            if '=' in pair:
                k, v = pair.split('=', 1)
                params[k.strip()] = v.strip()
    return params


@app.route('/login', methods=['POST'])
def login(headers="", body=""):
    """
    Handle user login via POST request.

    Accepts JSON body: {"username": "...", "password": "..."}
    or url-encoded form: username=...&password=...

    Returns a session token on success, or 401 error on failure.
    """
    print("[SampleApp] Login attempt, body: {}".format(body[:80] if body else ""))

    data = _parse_body(body)
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        resp = {"status": "error", "message": "Missing username or password"}
        return json.dumps(resp).encode("utf-8")

    stored_hash = USER_DB.get(username)
    if stored_hash is None:
        print("[SampleApp] Unknown user: {}".format(username))
        resp = {"status": "error", "message": "Invalid credentials"}
        return json.dumps(resp).encode("utf-8")

    input_hash = _hash_password(password)
    if input_hash != stored_hash:
        print("[SampleApp] Wrong password for user: {}".format(username))
        resp = {"status": "error", "message": "Invalid credentials"}
        return json.dumps(resp).encode("utf-8")

    # Credentials OK — generate session token
    token = _make_token(username)
    SESSIONS[token] = username
    print("[SampleApp] Login success for user: {}, token: {}".format(username, token))

    resp = {
        "status": "ok",
        "message": "Welcome to the RESTful TCP WebApp",
        "username": username,
        "token": token,
    }
    return json.dumps(resp).encode("utf-8")


@app.route('/logout', methods=['POST'])
def logout(headers="", body=""):
    """
    Invalidate a session token.
    Expects JSON body: {"token": "..."}
    """
    data = _parse_body(body)
    token = data.get("token", "").strip()

    if token in SESSIONS:
        user = SESSIONS.pop(token)
        print("[SampleApp] Logged out user: {}".format(user))
        resp = {"status": "ok", "message": "Logged out"}
    else:
        resp = {"status": "error", "message": "Invalid or expired token"}

    return json.dumps(resp).encode("utf-8")


@app.route('/profile', methods=['GET'])
def profile(headers="", body=""):
    """
    Return profile info for authenticated user.
    Reads Authorization header: Bearer <token>
    """
    # headers is a CaseInsensitiveDict or similar
    auth_header = ""
    if hasattr(headers, 'get'):
        auth_header = headers.get("authorization", "")
    elif isinstance(headers, str):
        # parse inline
        for line in headers.splitlines():
            if line.lower().startswith("authorization:"):
                auth_header = line.split(":", 1)[1].strip()
                break

    token = ""
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()

    username = SESSIONS.get(token)
    if not username:
        resp = {"status": "error", "message": "Unauthorized"}
        return json.dumps(resp).encode("utf-8")

    resp = {
        "status": "ok",
        "username": username,
        "role": "admin" if username == "admin" else "student",
    }
    return json.dumps(resp).encode("utf-8")


@app.route("/echo", methods=["POST"])
def echo(headers="", body=""):
    """Echo back whatever JSON the client sends."""
    print("[SampleApp] echo received body: {}".format(body))
    try:
        message = json.loads(body)
        resp = {"received": message}
    except (json.JSONDecodeError, TypeError):
        resp = {"error": "Invalid JSON", "raw": body}
    return json.dumps(resp).encode("utf-8")


@app.route('/hello', methods=['PUT'])
async def hello(headers, body):
    """
    Async greeting endpoint via PUT request.
    Returns a sample user object.
    """
    print("[SampleApp] ['PUT'] **ASYNC** Hello, headers={} body={}".format(headers, body))
    resp = {"id": 1, "name": "Alice", "email": "alice@example.com"}
    return json.dumps(resp).encode("utf-8")


def create_sampleapp(ip, port):
    app.prepare_address(ip, port)
    app.run()
