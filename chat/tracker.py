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
chat.tracker
~~~~~~~~~~~~~~~~~

Tracker server for the hybrid peer-to-peer chat application.

The tracker keeps track of online peers and lets them discover each other.
Each peer registers with its username, IP and port; others can query the
peer list and connect directly (P2P) to chat.

Protocol (text lines over TCP):
    Client -> Tracker:
        REGISTER <username> <ip> <port>
        LIST
        UNREGISTER <username>
        PING

    Tracker -> Client:
        OK
        ERROR <reason>
        PEERS <json-encoded list of peers>
        PONG
"""

import socket
import threading
import json
import time

# {username: {"ip": ..., "port": ..., "last_seen": ...}}
_peers = {}
_peers_lock = threading.Lock()

# Timeout in seconds — remove peers who haven't pinged recently
PEER_TIMEOUT = 60


def _remove_stale_peers():
    """Remove peers that haven't sent PING within PEER_TIMEOUT seconds."""
    now = time.time()
    with _peers_lock:
        stale = [u for u, info in _peers.items() if now - info["last_seen"] > PEER_TIMEOUT]
        for u in stale:
            print("[Tracker] Removing stale peer: {}".format(u))
            del _peers[u]


def handle_tracker_client(conn, addr):
    """Handle one tracker client connection."""
    print("[Tracker] New connection from {}".format(addr))
    try:
        conn.settimeout(30)
        data = conn.recv(1024).decode('utf-8', errors='replace').strip()
        if not data:
            conn.close()
            return

        print("[Tracker] Received: {}".format(data))
        _remove_stale_peers()

        parts = data.split()
        command = parts[0].upper() if parts else ""

        if command == "REGISTER" and len(parts) == 4:
            username, peer_ip, peer_port = parts[1], parts[2], parts[3]
            try:
                peer_port = int(peer_port)
            except ValueError:
                conn.sendall("ERROR Invalid port\n".encode())
                return
            with _peers_lock:
                _peers[username] = {
                    "ip": peer_ip,
                    "port": peer_port,
                    "last_seen": time.time()
                }
            print("[Tracker] Registered peer {} at {}:{}".format(username, peer_ip, peer_port))
            conn.sendall("OK\n".encode())

        elif command == "UNREGISTER" and len(parts) == 2:
            username = parts[1]
            with _peers_lock:
                removed = _peers.pop(username, None)
            if removed:
                print("[Tracker] Unregistered peer: {}".format(username))
                conn.sendall("OK\n".encode())
            else:
                conn.sendall("ERROR Unknown peer\n".encode())

        elif command == "LIST":
            with _peers_lock:
                peer_list = [
                    {"username": u, "ip": info["ip"], "port": info["port"]}
                    for u, info in _peers.items()
                ]
            payload = "PEERS {}\n".format(json.dumps(peer_list))
            conn.sendall(payload.encode())

        elif command == "PING" and len(parts) == 2:
            username = parts[1]
            with _peers_lock:
                if username in _peers:
                    _peers[username]["last_seen"] = time.time()
            conn.sendall("PONG\n".encode())

        else:
            conn.sendall("ERROR Unknown command\n".encode())

    except Exception as e:
        print("[Tracker] Error handling client {}: {}".format(addr, e))
    finally:
        conn.close()


def run_tracker(ip, port):
    """Start the tracker server."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((ip, port))
    server.listen(50)
    print("[Tracker] Listening on {}:{}".format(ip, port))

    while True:
        try:
            conn, addr = server.accept()
            t = threading.Thread(target=handle_tracker_client, args=(conn, addr), daemon=True)
            t.start()
        except KeyboardInterrupt:
            break
        except Exception as e:
            print("[Tracker] accept error: {}".format(e))

    server.close()
