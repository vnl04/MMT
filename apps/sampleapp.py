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

Complete RESTful web application implementing Assignment 1 requirements:
  - Section 2.2: HTTP Authentication with session tokens + Set-Cookie (RFC 6265)
  - Section 2.3: Hybrid P2P Chat APIs (Client-Server + Peer-to-Peer paradigms)

API Endpoints:
  POST  /login          - Authenticate user, return session token + Set-Cookie
  POST  /logout         - Invalidate session token
  POST  /submit-info    - Peer registers its IP and port (tracker update)
  GET   /get-list       - Peer discovery: get list of active peers
  POST  /add-list       - Peer joins a channel
  POST  /connect-peer   - Initiate direct TCP connection to another peer
  POST  /send-peer      - Send message directly to a peer (P2P)
  POST  /broadcast-peer - Broadcast message to all connected peers
"""

import sys
import os
import json
import hashlib
import base64
import socket
import threading
import time

from daemon import AsynapRous

app = AsynapRous()

# ------------------------------------------------------------------
# User database: {username: hashed_password}
# ------------------------------------------------------------------
def _hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

USER_DB = {
    "admin":   _hash_password("admin123"),
    "student": _hash_password("hcmut2026"),
    "alice":   _hash_password("alice123"),
    "bob":     _hash_password("bob123"),
    "guest":   _hash_password("guest"),
}

# ------------------------------------------------------------------
# Session store: {token: username}      (RFC 6265 - Cookie sessions)
# ------------------------------------------------------------------
SESSIONS = {}

# ------------------------------------------------------------------
# Peer registry: {username: {"ip": ..., "port": ..., "last_seen": ...}}
# This replaces the standalone tracker for the Web-based P2P chat
# ------------------------------------------------------------------
PEER_REGISTRY = {}
_registry_lock = threading.Lock()

PEER_TIMEOUT = 120   # seconds before a peer is considered offline

# ------------------------------------------------------------------
# Channel store: {channel_name: [username, ...]}
# ------------------------------------------------------------------
CHANNELS = {"general": []}
_channel_lock = threading.Lock()

# ------------------------------------------------------------------
# Message store: {channel_name: [{from, text, time}, ...]}
# ------------------------------------------------------------------
MESSAGES = {"general": []}
_msg_lock = threading.Lock()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_token(username):
    """Generate a unique session token."""
    raw = "{}:{}".format(username, os.urandom(8).hex())
    return base64.b64encode(raw.encode()).decode()


def _parse_body(body):
    """Try to parse body as JSON, fall back to url-encoded form."""
    try:
        return json.loads(body)
    except (json.JSONDecodeError, TypeError):
        pass
    params = {}
    if body:
        for pair in body.split('&'):
            pair = pair.strip()
            if '=' in pair:
                k, v = pair.split('=', 1)
                params[k.strip()] = v.strip()
    return params


def _get_username_from_session(headers):
    """Extract username from Authorization or Cookie header."""
    # Try Bearer token first
    auth = ""
    if hasattr(headers, 'get'):
        auth = headers.get("authorization", "") or headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        return SESSIONS.get(token)

    # Try Cookie: session=<token>
    cookie_str = ""
    if hasattr(headers, 'get'):
        cookie_str = headers.get("cookie", "") or headers.get("Cookie", "")
    if cookie_str:
        for pair in cookie_str.split(';'):
            pair = pair.strip()
            if pair.lower().startswith("session="):
                token = pair.split('=', 1)[1].strip()
                return SESSIONS.get(token)

    return None


def _remove_stale_peers():
    """Remove peers that haven't pinged recently."""
    now = time.time()
    with _registry_lock:
        stale = [u for u, info in PEER_REGISTRY.items()
                 if now - info.get("last_seen", 0) > PEER_TIMEOUT]
        for u in stale:
            print("[SampleApp] Removing stale peer: {}".format(u))
            del PEER_REGISTRY[u]


def _direct_send(peer_ip, peer_port, payload_str):
    """Open a short-lived TCP socket to send a message directly to a peer (P2P)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((peer_ip, int(peer_port)))
        s.sendall((payload_str + "\n").encode('utf-8'))
        reply = s.recv(256).decode('utf-8', errors='replace').strip()
        s.close()
        return True, reply
    except Exception as e:
        return False, str(e)


# ------------------------------------------------------------------
# 2.2 — Authentication endpoints (RFC 2617 / RFC 6265)
# ------------------------------------------------------------------

@app.route('/login', methods=['POST'])
def login(headers="", body=""):
    """
    POST /login
    Authenticate user with username + password.

    Request body (JSON or form-encoded):
        {"username": "alice", "password": "alice123"}

    Returns:
        {"status": "ok", "token": "...", "username": "..."}
        + Set-Cookie: session=<token>; Path=/; HttpOnly
    """
    print("[SampleApp] /login attempt")
    data = _parse_body(body)
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        resp = {"status": "error", "message": "Missing username or password"}
        return json.dumps(resp).encode("utf-8")

    stored_hash = USER_DB.get(username)
    if stored_hash is None or _hash_password(password) != stored_hash:
        print("[SampleApp] Login failed for: {}".format(username))
        resp = {"status": "error", "message": "Invalid credentials"}
        return json.dumps(resp).encode("utf-8")

    # Valid credentials — issue session token
    token = _make_token(username)
    SESSIONS[token] = username
    print("[SampleApp] Login OK for {}, token={}".format(username, token[:16] + "..."))

    resp_data = {
        "status": "ok",
        "message": "Welcome to AsynapRous!",
        "username": username,
        "token": token,
    }
    # Return (body, extra_headers) tuple so httpadapter sets the cookie
    cookie_str = "session={}; Path=/; HttpOnly".format(token)
    return (
        json.dumps(resp_data).encode("utf-8"),
        {"Set-Cookie": cookie_str}
    )


@app.route('/logout', methods=['POST'])
def logout(headers="", body=""):
    """
    POST /logout
    Invalidate session token.

    Request body: {"token": "..."} OR relies on Cookie header.
    """
    data = _parse_body(body)
    token = data.get("token", "").strip()

    # Also check headers
    if not token:
        auth = ""
        if hasattr(headers, 'get'):
            auth = headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()

    if token in SESSIONS:
        user = SESSIONS.pop(token)
        print("[SampleApp] Logged out: {}".format(user))
        resp = {"status": "ok", "message": "Logged out"}
    else:
        resp = {"status": "error", "message": "Invalid or expired token"}

    return (
        json.dumps(resp).encode("utf-8"),
        {"Set-Cookie": "session=; Path=/; HttpOnly; Max-Age=0"}
    )


# ------------------------------------------------------------------
# 2.3 — Hybrid P2P Chat endpoints
# ------------------------------------------------------------------

@app.route('/submit-info', methods=['POST'])
def submit_info(headers="", body=""):
    """
    POST /submit-info
    Peer registers its listening IP and port with the tracker (this server).

    Initialization phase — Client-Server paradigm.

    Request body (JSON):
        {"username": "alice", "ip": "127.0.0.1", "port": 7001, "token": "..."}

    Returns:
        {"status": "ok", "message": "Registered"}
    """
    print("[SampleApp] /submit-info")
    data = _parse_body(body)

    # Auth check
    username_from_session = _get_username_from_session(headers)
    username = data.get("username", username_from_session or "").strip()
    if not username:
        return json.dumps({"status": "error", "message": "Unauthorized"}).encode("utf-8")

    peer_ip   = data.get("ip", "127.0.0.1").strip()
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
    resp = {"status": "ok", "message": "Registered as {} at {}:{}".format(username, peer_ip, peer_port)}
    return json.dumps(resp).encode("utf-8")


@app.route('/get-list', methods=['GET'])
def get_list(headers="", body=""):
    """
    GET /get-list
    Peer discovery — return list of all active peers.

    Initialization phase — Client-Server paradigm.

    Returns:
        {"status": "ok", "peers": [{"username": ..., "ip": ..., "port": ...}, ...]}
    """
    print("[SampleApp] /get-list")
    _remove_stale_peers()

    with _registry_lock:
        peers = [
            {"username": u, "ip": info["ip"], "port": info["port"]}
            for u, info in PEER_REGISTRY.items()
        ]

    resp = {"status": "ok", "peers": peers}
    return json.dumps(resp).encode("utf-8")


@app.route('/add-list', methods=['POST'])
def add_list(headers="", body=""):
    """
    POST /add-list
    Peer joins a channel (channel management).

    Request body (JSON):
        {"username": "alice", "channel": "general"}

    Returns:
        {"status": "ok", "channel": "general", "members": [...]}
    """
    print("[SampleApp] /add-list")
    data = _parse_body(body)

    username = data.get("username", "").strip()
    channel  = data.get("channel", "general").strip()

    if not username:
        username = _get_username_from_session(headers) or "anonymous"

    with _channel_lock:
        if channel not in CHANNELS:
            CHANNELS[channel] = []
            MESSAGES[channel] = []
        if username not in CHANNELS[channel]:
            CHANNELS[channel].append(username)

    print("[SampleApp] {} joined channel '{}'".format(username, channel))
    resp = {
        "status": "ok",
        "channel": channel,
        "members": CHANNELS.get(channel, [])
    }
    return json.dumps(resp).encode("utf-8")


@app.route('/connect-peer', methods=['POST'])
def connect_peer(headers="", body=""):
    """
    POST /connect-peer
    Initiate direct connection probe to a target peer (Peer-to-Peer setup).

    Connection setup phase — P2P paradigm.

    Request body (JSON):
        {"target": "bob"}

    Returns:
        {"status": "ok"|"error", "target": ..., "ip": ..., "port": ...}
    """
    print("[SampleApp] /connect-peer")
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
            "message": "Peer '{}' not found or offline".format(target)
        }).encode("utf-8")

    # Probe connection
    ok, reply = _direct_send(peer_info["ip"], peer_info["port"], "PING")
    status = "ok" if ok else "error"
    resp = {
        "status": status,
        "target": target,
        "ip": peer_info["ip"],
        "port": peer_info["port"],
        "probe": reply,
    }
    return json.dumps(resp).encode("utf-8")


@app.route('/send-peer', methods=['POST'])
def send_peer(headers="", body=""):
    """
    POST /send-peer
    Send a message directly to a specific peer over TCP (P2P direct communication).

    Peer chatting phase — P2P paradigm.
    Messages are NOT routed through this server; backend opens a direct TCP
    connection to the target peer daemon.

    Request body (JSON):
        {"from": "alice", "target": "bob", "message": "Hello Bob!",
         "channel": "general"}

    Returns:
        {"status": "ok"|"error", "delivered": true|false}
    """
    print("[SampleApp] /send-peer")
    data = _parse_body(body)

    sender  = data.get("from", "").strip()
    target  = data.get("target", "").strip()
    message = data.get("message", "").strip()
    channel = data.get("channel", "general").strip()

    if not sender:
        sender = _get_username_from_session(headers) or "anonymous"

    if not target or not message:
        return json.dumps({
            "status": "error", "message": "Missing target or message"
        }).encode("utf-8")

    # Store message locally regardless of delivery
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
        # Target not registered — store and return (message stored server-side)
        resp = {
            "status": "ok",
            "delivered": False,
            "message": "Peer '{}' offline; message stored".format(target),
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


@app.route('/broadcast-peer', methods=['POST'])
def broadcast_peer(headers="", body=""):
    """
    POST /broadcast-peer
    Broadcast message to ALL active peers (P2P broadcast connection).

    Peer chatting phase — P2P paradigm.

    Request body (JSON):
        {"from": "alice", "message": "Hello everyone!", "channel": "general"}

    Returns:
        {"status": "ok", "results": {peer: delivered_bool, ...}}
    """
    print("[SampleApp] /broadcast-peer")
    data = _parse_body(body)

    sender  = data.get("from", "").strip()
    message = data.get("message", "").strip()
    channel = data.get("channel", "general").strip()

    if not sender:
        sender = _get_username_from_session(headers) or "anonymous"

    if not message:
        return json.dumps({
            "status": "error", "message": "Missing message"
        }).encode("utf-8")

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
        print("[SampleApp] Broadcast -> {} : {}".format(uname, "OK" if ok else "FAIL"))

    threads = []
    for uname, info in peers_snapshot.items():
        t = threading.Thread(target=_send_one, args=(uname, info), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join(timeout=6)

    resp = {"status": "ok", "sender": sender, "results": results}
    return json.dumps(resp).encode("utf-8")


@app.route('/messages', methods=['GET'])
def get_messages(headers="", body=""):
    """
    GET /messages
    Retrieve stored messages for a channel (polling for new messages).

    Query: channel name passed via body JSON {"channel": "general"}
    Returns:
        {"status": "ok", "messages": [...], "channel": "general"}
    """
    data = _parse_body(body) if body else {}
    channel = data.get("channel", "general").strip()

    with _msg_lock:
        msgs = list(MESSAGES.get(channel, []))

    resp = {"status": "ok", "channel": channel, "messages": msgs}
    return json.dumps(resp).encode("utf-8")


@app.route('/ping', methods=['POST'])
def ping_peer(headers="", body=""):
    """
    POST /ping
    Heartbeat — peer pings to stay alive in the registry.

    Request body: {"username": "alice"}
    Returns: {"status": "ok", "pong": true}
    """
    data = _parse_body(body)
    username = data.get("username", "").strip()
    if not username:
        username = _get_username_from_session(headers) or ""

    if username and username in PEER_REGISTRY:
        with _registry_lock:
            PEER_REGISTRY[username]["last_seen"] = time.time()

    return json.dumps({"status": "ok", "pong": True}).encode("utf-8")


def create_sampleapp(ip, port):
    """Entry point: configure address and launch the AsynapRous server."""
    app.prepare_address(ip, port)
    app.run()
