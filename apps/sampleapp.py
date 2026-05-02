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

Complete RESTful web application implementing Assignment 1 requirements.

Merged fixes (from ``files/`` patch set + RFC tidy-ups):
    * ``AsynapRous.route`` returns the handler unchanged (correct async introspection).
    * Request routing normalises trailing slashes (``/login/`` ≡ ``/login``).
    * ``HttpAdapter``: optional ``raw=`` pre-read buffer; asyncio mode uses ``self.routes``.
    * Proxy: recv timeout + deduped ``proxy_pass`` in ``start_proxy.py``.
    * Login failures return ``401`` JSON + ``WWW-Authenticate``; missing fields → ``400``.
    * ``/logout`` accepts ``Cookie: session=`` as well as body / Bearer token.
    * ``/messages`` registered once for GET and POST.

  Section 2.2 — Authentication (RFC 2617 / RFC 7235 / RFC 6265)
    * Basic auth via ``Authorization: Basic <b64>`` header.
    * Session token issued on login; stored in ``Set-Cookie: session=<token>``.
    * Failed login responds with ``401`` + ``WWW-Authenticate`` (RFC 7235).

  Section 2.3 — Hybrid P2P Chat
    Initialization phase (Client-Server):
      POST /login          — authenticate, issue token + cookie
      POST /logout         — invalidate session
      POST /submit-info    — peer registers its listen IP:port
      GET  /get-list       — discover active peers
      POST /add-list       — join a channel

    P2P chatting phase (Peer-to-Peer):
      POST /connect-peer   — probe direct TCP connection to a peer
      POST /send-peer      — send message directly via TCP to one peer
      POST /broadcast-peer — broadcast message to all active peers

    Utility:
      GET  /messages       — poll stored messages for a channel
      POST /messages       — same, body-based channel selection
      POST /ping           — heartbeat to keep peer alive in registry

API endpoints listed in assignment §2.3:
  http://IP:port/login/
  http://IP:port/submit-info/
  http://IP:port/add-list/
  http://IP:port/get-list/
  http://IP:port/connect-peer/
  http://IP:port/broadcast-peer/
  http://IP:port/send-peer/
"""

import os
import json
import hashlib
import base64
import socket
import threading
import time

from daemon import AsynapRous

app = AsynapRous()

# ---------------------------------------------------------------------------
# User database   {username: sha256(password)}
# ---------------------------------------------------------------------------

def _hash_password(pw):
    """Return hex SHA-256 digest of *pw*."""
    return hashlib.sha256(pw.encode()).hexdigest()


USER_DB = {
    "admin":   _hash_password("admin123"),
    "student": _hash_password("hcmut2026"),
    "alice":   _hash_password("alice123"),
    "bob":     _hash_password("bob123"),
    "guest":   _hash_password("guest"),
}

# ---------------------------------------------------------------------------
# Session store  {token: username}   (RFC 6265 cookie sessions)
# ---------------------------------------------------------------------------
SESSIONS = {}

# ---------------------------------------------------------------------------
# Peer registry  {username: {"ip": .., "port": .., "last_seen": ..}}
# ---------------------------------------------------------------------------
PEER_REGISTRY = {}
_registry_lock = threading.Lock()
PEER_TIMEOUT = 120          # seconds before peer is considered offline

# ---------------------------------------------------------------------------
# Channel store  {channel_name: [username, ...]}
# ---------------------------------------------------------------------------
CHANNELS = {"general": []}
_channel_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Message store  {channel_name: [{from, text, time, channel}, ...]}
# ---------------------------------------------------------------------------
MESSAGES = {"general": []}
_msg_lock = threading.Lock()


# ===========================================================================
# Internal helpers
# ===========================================================================

def _make_token(username):
    """Generate a random, opaque session token for *username*."""
    raw = "{}:{}".format(username, os.urandom(8).hex())
    return base64.b64encode(raw.encode()).decode()


def _parse_body(body):
    """Try JSON first, then fall back to URL-encoded form parsing.

    :param body: Request body string.
    :returns: ``dict`` of parsed key/value pairs.
    """
    try:
        return json.loads(body)
    except (json.JSONDecodeError, TypeError):
        pass
    params = {}
    if body:
        for pair in body.split("&"):
            pair = pair.strip()
            if "=" in pair:
                k, v = pair.split("=", 1)
                params[k.strip()] = v.strip()
    return params


def _get_username_from_session(headers):
    """Extract the authenticated username from request *headers*.

    Checks, in order:
      1. ``Authorization: Bearer <token>``
      2. ``Cookie: session=<token>``
      3. ``Authorization: Basic <b64(user:pass)>``  (RFC 2617)

    :param headers: :class:`CaseInsensitiveDict` of request headers.
    :returns: Username string, or ``None`` if unauthenticated.
    """
    if not headers:
        return None

    auth = ""
    if hasattr(headers, "get"):
        auth = headers.get("authorization", "")

    # Bearer token
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        return SESSIONS.get(token)

    # Cookie session
    cookie_str = headers.get("cookie", "") if hasattr(headers, "get") else ""
    if cookie_str:
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            if pair.lower().startswith("session="):
                token = pair.split("=", 1)[1].strip()
                return SESSIONS.get(token)

    # HTTP Basic Auth (RFC 2617)
    if auth.lower().startswith("basic "):
        try:
            decoded = base64.b64decode(auth[6:].strip()).decode("utf-8", errors="replace")
            username, _, password = decoded.partition(":")
            stored = USER_DB.get(username)
            if stored and _hash_password(password) == stored:
                return username
        except Exception:
            pass

    return None


def _session_token_from_cookie(headers):
    """Return the opaque ``session`` cookie value if present (RFC 6265)."""
    if not headers or not hasattr(headers, "get"):
        return ""
    cookie_str = headers.get("cookie", "")
    if not cookie_str:
        return ""
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if pair.lower().startswith("session="):
            return pair.split("=", 1)[1].strip()
    return ""


def _remove_stale_peers():
    """Remove peers that have not sent a heartbeat within ``PEER_TIMEOUT``."""
    now = time.time()
    with _registry_lock:
        stale = [u for u, info in PEER_REGISTRY.items()
                 if now - info.get("last_seen", 0) > PEER_TIMEOUT]
        for u in stale:
            print("[SampleApp] Removing stale peer: {}".format(u))
            del PEER_REGISTRY[u]


def _direct_send(peer_ip, peer_port, payload_str):
    """Open a short-lived TCP socket and send *payload_str* directly to a peer.

    Implements the **direct peer communication** requirement from §2.3.

    :param peer_ip: Target IP string.
    :param peer_port: Target port integer.
    :param payload_str: JSON payload string to send.
    :returns: ``(success_bool, reply_string)`` tuple.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((peer_ip, int(peer_port)))
        s.sendall((payload_str + "\n").encode("utf-8"))
        reply = s.recv(256).decode("utf-8", errors="replace").strip()
        s.close()
        return True, reply
    except Exception as e:
        return False, str(e)


# ===========================================================================
# 2.2 — Authentication endpoints
# ===========================================================================

@app.route("/login", methods=["POST"])
def login(headers="", body=""):
    """Authenticate a user and issue a session token.

    Accepts JSON body ``{"username": "alice", "password": "alice123"}``.

    On success returns JSON ``{"status": "ok", "token": "...", "username": "..."}`
    plus the response header ``Set-Cookie: session=<token>; Path=/; HttpOnly``
    as required by RFC 6265.

    :param headers: Request headers (CaseInsensitiveDict).
    :param body: Raw request body string.
    :returns: ``(json_bytes, extra_headers)`` tuple.
    """
    print("[SampleApp] POST /login")
    data = _parse_body(body)
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        resp = {"status": "error", "message": "Missing username or password"}
        return (
            json.dumps(resp).encode("utf-8"),
            {"__status": "400", "__reason": "Bad Request"},
        )

    stored = USER_DB.get(username)
    if stored is None or _hash_password(password) != stored:
        print("[SampleApp] Login failed for: {}".format(username))
        resp = {"status": "error", "message": "Invalid credentials"}
        return (
            json.dumps(resp).encode("utf-8"),
            {
                "WWW-Authenticate": 'Basic realm="AsynapRous"',
                "__status": "401",
                "__reason": "Unauthorized",
            },
        )

    token = _make_token(username)
    SESSIONS[token] = username
    print("[SampleApp] Login OK for {}, token prefix={}".format(username, token[:16]))

    resp_data = {
        "status": "ok",
        "message": "Welcome to AsynapRous!",
        "username": username,
        "token": token,
    }
    # RFC 6265 §4.1 — Set-Cookie with HttpOnly flag
    cookie_str = "session={}; Path=/; HttpOnly".format(token)
    return (
        json.dumps(resp_data).encode("utf-8"),
        {"Set-Cookie": cookie_str},
    )


@app.route("/logout", methods=["POST"])
def logout(headers="", body=""):
    """Invalidate the caller's session token.

    Accepts ``{"token": "..."}`` in the body, or reads from the
    ``Authorization`` / ``Cookie`` header.

    :param headers: Request headers.
    :param body: Raw request body string.
    :returns: ``(json_bytes, extra_headers)`` — clears the session cookie.
    """
    print("[SampleApp] POST /logout")
    data = _parse_body(body)
    token = data.get("token", "").strip()

    # Fall back to Authorization header
    if not token and hasattr(headers, "get"):
        auth = headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()

    if not token:
        token = _session_token_from_cookie(headers)

    if token in SESSIONS:
        user = SESSIONS.pop(token)
        print("[SampleApp] Logged out: {}".format(user))
        resp = {"status": "ok", "message": "Logged out"}
    else:
        resp = {"status": "error", "message": "Invalid or expired token"}

    # RFC 6265 — expire the cookie
    return (
        json.dumps(resp).encode("utf-8"),
        {"Set-Cookie": "session=; Path=/; HttpOnly; Max-Age=0"},
    )


# ===========================================================================
# 2.3 — Hybrid P2P Chat: Initialization phase (Client-Server)
# ===========================================================================

@app.route("/submit-info", methods=["POST"])
def submit_info(headers="", body=""):
    """Register this peer's listen address with the tracker.

    **Initialization phase — Client-Server paradigm.**

    Accepts ``{"username": "alice", "ip": "127.0.0.1", "port": 7001}``.

    :param headers: Request headers (used for auth fallback).
    :param body: Raw request body string.
    :returns: JSON response bytes.
    """
    print("[SampleApp] POST /submit-info")
    data = _parse_body(body)

    username = data.get("username", "").strip()
    if not username:
        username = _get_username_from_session(headers) or ""
    if not username:
        return json.dumps({"status": "error", "message": "Unauthorized"}).encode("utf-8")

    peer_ip = data.get("ip", "127.0.0.1").strip()
    peer_port = data.get("port", 0)
    try:
        peer_port = int(peer_port)
    except (ValueError, TypeError):
        return json.dumps({"status": "error", "message": "Invalid port"}).encode("utf-8")

    _remove_stale_peers()

    with _registry_lock:
        PEER_REGISTRY[username] = {
            "ip": peer_ip,
            "port": peer_port,
            "last_seen": time.time(),
        }

    print("[SampleApp] Registered peer {} at {}:{}".format(username, peer_ip, peer_port))
    resp = {
        "status": "ok",
        "message": "Registered {} at {}:{}".format(username, peer_ip, peer_port),
    }
    return json.dumps(resp).encode("utf-8")


@app.route("/get-list", methods=["GET"])
def get_list(headers="", body=""):
    """Return the list of currently active peers.

    **Initialization phase — Client-Server paradigm (peer discovery).**

    :param headers: Request headers.
    :param body: Unused.
    :returns: JSON ``{"status": "ok", "peers": [...]}`` bytes.
    """
    print("[SampleApp] GET /get-list")
    _remove_stale_peers()

    with _registry_lock:
        peers = [
            {"username": u, "ip": info["ip"], "port": info["port"]}
            for u, info in PEER_REGISTRY.items()
        ]

    resp = {"status": "ok", "peers": peers}
    return json.dumps(resp).encode("utf-8")


@app.route("/add-list", methods=["POST"])
def add_list(headers="", body=""):
    """Add a peer to a channel (channel management).

    **Initialization phase — Client-Server paradigm.**

    Accepts ``{"username": "alice", "channel": "general"}``.

    :param headers: Request headers.
    :param body: Raw request body string.
    :returns: JSON ``{"status": "ok", "channel": ..., "members": [...]}`` bytes.
    """
    print("[SampleApp] POST /add-list")
    data = _parse_body(body)

    username = data.get("username", "").strip()
    channel = data.get("channel", "general").strip()

    if not username:
        username = _get_username_from_session(headers) or "anonymous"

    with _channel_lock:
        if channel not in CHANNELS:
            CHANNELS[channel] = []
            with _msg_lock:
                MESSAGES[channel] = []
        if username not in CHANNELS[channel]:
            CHANNELS[channel].append(username)

    print("[SampleApp] {} joined channel '{}'".format(username, channel))
    resp = {
        "status": "ok",
        "channel": channel,
        "members": list(CHANNELS.get(channel, [])),
    }
    return json.dumps(resp).encode("utf-8")


# ===========================================================================
# 2.3 — Hybrid P2P Chat: P2P chatting phase
# ===========================================================================

@app.route("/connect-peer", methods=["POST"])
def connect_peer(headers="", body=""):
    """Probe a direct TCP connection to a peer (connection setup).

    **P2P paradigm — connection setup phase.**

    Accepts ``{"target": "bob"}``.

    :param headers: Request headers.
    :param body: Raw request body string.
    :returns: JSON with peer address and probe result.
    """
    print("[SampleApp] POST /connect-peer")
    data = _parse_body(body)
    target = data.get("target", "").strip()

    if not target:
        return json.dumps({"status": "error", "message": "No target specified"}).encode("utf-8")

    _remove_stale_peers()

    with _registry_lock:
        peer_info = PEER_REGISTRY.get(target)

    if not peer_info:
        return json.dumps({
            "status": "error",
            "message": "Peer '{}' not found or offline".format(target),
        }).encode("utf-8")

    ok, reply = _direct_send(peer_info["ip"], peer_info["port"], "PING")
    resp = {
        "status": "ok" if ok else "error",
        "target": target,
        "ip": peer_info["ip"],
        "port": peer_info["port"],
        "probe": reply,
    }
    return json.dumps(resp).encode("utf-8")


@app.route("/send-peer", methods=["POST"])
def send_peer(headers="", body=""):
    """Send a message directly to one peer via TCP (direct P2P communication).

    **P2P paradigm — chatting phase.**

    The backend opens a direct TCP connection to the target peer daemon;
    the message is **not** routed through this server.

    Accepts ``{"from": "alice", "target": "bob", "message": "Hi!", "channel": "general"}``.

    :param headers: Request headers.
    :param body: Raw request body string.
    :returns: JSON delivery report bytes.
    """
    print("[SampleApp] POST /send-peer")
    data = _parse_body(body)

    sender = data.get("from", "").strip()
    target = data.get("target", "").strip()
    message = data.get("message", "").strip()
    channel = data.get("channel", "general").strip()

    if not sender:
        sender = _get_username_from_session(headers) or "anonymous"
    if not target or not message:
        return json.dumps({"status": "error", "message": "Missing target or message"}).encode("utf-8")

    # Store message server-side regardless of P2P delivery success
    timestamp = time.strftime("%H:%M:%S")
    entry = {"from": sender, "text": message, "time": timestamp, "channel": channel}
    with _msg_lock:
        if channel not in MESSAGES:
            MESSAGES[channel] = []
        MESSAGES[channel].append(entry)

    _remove_stale_peers()
    with _registry_lock:
        peer_info = PEER_REGISTRY.get(target)

    if not peer_info:
        resp = {
            "status": "ok",
            "delivered": False,
            "message": "Peer '{}' offline; message stored server-side".format(target),
        }
        return json.dumps(resp).encode("utf-8")

    # P2P direct send — bypass this server
    payload = json.dumps({"from": sender, "text": message,
                          "time": timestamp, "channel": channel})
    ok, reply = _direct_send(peer_info["ip"], peer_info["port"], payload)

    resp = {
        "status": "ok" if ok else "error",
        "delivered": ok,
        "target": target,
        "reply": reply,
    }
    return json.dumps(resp).encode("utf-8")


@app.route("/broadcast-peer", methods=["POST"])
def broadcast_peer(headers="", body=""):
    """Broadcast a message to ALL active peers (P2P broadcast connection).

    **P2P paradigm — chatting phase.**

    Each peer is contacted concurrently via a dedicated daemon thread.

    Accepts ``{"from": "alice", "message": "Hello everyone!", "channel": "general"}``.

    :param headers: Request headers.
    :param body: Raw request body string.
    :returns: JSON with per-peer delivery results.
    """
    print("[SampleApp] POST /broadcast-peer")
    data = _parse_body(body)

    sender = data.get("from", "").strip()
    message = data.get("message", "").strip()
    channel = data.get("channel", "general").strip()

    if not sender:
        sender = _get_username_from_session(headers) or "anonymous"
    if not message:
        return json.dumps({"status": "error", "message": "Missing message"}).encode("utf-8")

    timestamp = time.strftime("%H:%M:%S")
    entry = {"from": sender, "text": message, "time": timestamp, "channel": channel}
    with _msg_lock:
        if channel not in MESSAGES:
            MESSAGES[channel] = []
        MESSAGES[channel].append(entry)

    _remove_stale_peers()
    with _registry_lock:
        peers_snapshot = dict(PEER_REGISTRY)

    payload = json.dumps({"from": sender, "text": message,
                          "time": timestamp, "channel": channel})
    results = {}

    def _send_one(uname, info):
        if uname == sender:
            return
        ok, _ = _direct_send(info["ip"], info["port"], payload)
        results[uname] = ok
        print("[SampleApp] Broadcast -> {}: {}".format(uname, "OK" if ok else "FAIL"))

    # Concurrent broadcast — one thread per peer
    threads = [
        threading.Thread(target=_send_one, args=(u, info), daemon=True)
        for u, info in peers_snapshot.items()
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=6)

    resp = {"status": "ok", "sender": sender, "results": results}
    return json.dumps(resp).encode("utf-8")


# ===========================================================================
# Utility endpoints
# ===========================================================================

@app.route("/messages", methods=["GET", "POST"])
def get_messages(headers="", body=""):
    """Return stored messages for a channel (polling endpoint).

    Supports both GET and POST so the browser's ``fetch()`` works for both
    cases.  The channel name is read from the JSON body; defaults to
    ``"general"``.

    **Bug fix**: GET requests from browsers send no body, so the channel
    must default gracefully to ``"general"`` rather than crashing.

    :param headers: Request headers.
    :param body: Optional JSON body ``{"channel": "general"}``.
    :returns: JSON ``{"status": "ok", "channel": ..., "messages": [...]}`` bytes.
    """
    data = _parse_body(body) if body and body.strip() else {}
    channel = data.get("channel", "general").strip() if data else "general"

    with _msg_lock:
        msgs = list(MESSAGES.get(channel, []))

    resp = {"status": "ok", "channel": channel, "messages": msgs}
    return json.dumps(resp).encode("utf-8")


@app.route("/ping", methods=["POST"])
def ping_peer(headers="", body=""):
    """Heartbeat — refresh a peer's ``last_seen`` timestamp in the registry.

    Accepts ``{"username": "alice"}``.

    :param headers: Request headers (auth fallback).
    :param body: Raw request body string.
    :returns: JSON ``{"status": "ok", "pong": true}`` bytes.
    """
    data = _parse_body(body)
    username = data.get("username", "").strip()
    if not username:
        username = _get_username_from_session(headers) or ""

    if username and username in PEER_REGISTRY:
        with _registry_lock:
            PEER_REGISTRY[username]["last_seen"] = time.time()

    return json.dumps({"status": "ok", "pong": True}).encode("utf-8")


# ===========================================================================
# Entry point
# ===========================================================================

def create_sampleapp(ip, port):
    """Configure and start the AsynapRous server.

    :param ip: IP address to bind, e.g. ``'0.0.0.0'``.
    :param port: Port to listen on, e.g. ``2026``.
    """
    app.prepare_address(ip, port)
    app.run()
