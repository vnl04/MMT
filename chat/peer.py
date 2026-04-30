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
chat.peer
~~~~~~~~~~~~~~~~~

Peer node for the hybrid peer-to-peer chat application.

Each peer:
  1. Registers itself with the tracker (server-side coordination).
  2. Listens on its own TCP port for incoming direct messages from other peers.
  3. Allows the user to list online peers and send messages directly (P2P).

Usage:
    python start_peer.py --username alice --peer-port 7001 \
                         --tracker-ip 127.0.0.1 --tracker-port 6000
"""

import socket
import threading
import json
import time
import sys


class ChatPeer:
    """A single chat peer that connects to a tracker and talks P2P to others."""

    def __init__(self, username, peer_ip, peer_port, tracker_ip, tracker_port):
        self.username = username
        self.peer_ip = peer_ip
        self.peer_port = peer_port
        self.tracker_ip = tracker_ip
        self.tracker_port = tracker_port

        self._running = False
        self._listen_sock = None
        self._ping_thread = None
        self._listen_thread = None

    # ------------------------------------------------------------------
    # Tracker communication helpers
    # ------------------------------------------------------------------

    def _tracker_send(self, message):
        """Open a short-lived connection to the tracker, send message, return reply."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect((self.tracker_ip, self.tracker_port))
            s.sendall((message + "\n").encode())
            reply = s.recv(4096).decode('utf-8', errors='replace').strip()
            s.close()
            return reply
        except Exception as e:
            print("[Peer] Tracker communication error: {}".format(e))
            return None

    def register(self):
        """Register this peer with the tracker."""
        msg = "REGISTER {} {} {}".format(self.username, self.peer_ip, self.peer_port)
        reply = self._tracker_send(msg)
        if reply == "OK":
            print("[Peer] Registered as '{}' at {}:{}".format(
                self.username, self.peer_ip, self.peer_port))
            return True
        print("[Peer] Registration failed: {}".format(reply))
        return False

    def unregister(self):
        """Unregister from the tracker on shutdown."""
        reply = self._tracker_send("UNREGISTER {}".format(self.username))
        print("[Peer] Unregistered: {}".format(reply))

    def list_peers(self):
        """Query tracker for online peers."""
        reply = self._tracker_send("LIST")
        if reply and reply.startswith("PEERS "):
            try:
                peers = json.loads(reply[6:])
                return peers
            except json.JSONDecodeError:
                return []
        return []

    def _ping_loop(self, interval=15):
        """Send periodic PING to tracker to stay registered."""
        while self._running:
            self._tracker_send("PING {}".format(self.username))
            time.sleep(interval)

    # ------------------------------------------------------------------
    # P2P listener — accepts incoming messages from other peers
    # ------------------------------------------------------------------

    def _listen_loop(self):
        """Listen for direct incoming messages from other peers."""
        self._listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listen_sock.bind((self.peer_ip, self.peer_port))
        self._listen_sock.listen(10)
        self._listen_sock.settimeout(1.0)   # non-blocking accept loop
        print("[Peer] Listening for peers on {}:{}".format(self.peer_ip, self.peer_port))

        while self._running:
            try:
                conn, addr = self._listen_sock.accept()
                t = threading.Thread(target=self._handle_incoming, args=(conn, addr), daemon=True)
                t.start()
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    print("[Peer] Listen error: {}".format(e))
                break

        self._listen_sock.close()

    def _handle_incoming(self, conn, addr):
        """Receive and display a message from another peer."""
        try:
            conn.settimeout(10)
            data = conn.recv(4096).decode('utf-8', errors='replace').strip()
            if data:
                try:
                    msg = json.loads(data)
                    sender = msg.get("from", "unknown")
                    text = msg.get("text", "")
                    print("\n[{}] {}: {}".format(
                        time.strftime("%H:%M:%S"), sender, text))
                except json.JSONDecodeError:
                    print("\n[raw message from {}] {}".format(addr, data))
            conn.sendall("ACK\n".encode())
        except Exception as e:
            print("[Peer] Incoming message error: {}".format(e))
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Send a direct P2P message to another peer
    # ------------------------------------------------------------------

    def send_message(self, target_username, text):
        """Look up target peer and send them a message directly."""
        peers = self.list_peers()
        target = None
        for p in peers:
            if p["username"] == target_username:
                target = p
                break

        if not target:
            print("[Peer] User '{}' is not online".format(target_username))
            return False

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect((target["ip"], target["port"]))
            payload = json.dumps({"from": self.username, "text": text})
            s.sendall((payload + "\n").encode())
            reply = s.recv(64).decode().strip()
            s.close()
            if reply == "ACK":
                print("[Peer] Message delivered to '{}'".format(target_username))
                return True
        except Exception as e:
            print("[Peer] Failed to send to {}: {}".format(target_username, e))
        return False

    # ------------------------------------------------------------------
    # Start / stop
    # ------------------------------------------------------------------

    def start(self):
        """Register with tracker and start background threads."""
        if not self.register():
            return False

        self._running = True

        self._listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listen_thread.start()

        self._ping_thread = threading.Thread(target=self._ping_loop, daemon=True)
        self._ping_thread.start()

        return True

    def stop(self):
        """Unregister and stop background threads."""
        self._running = False
        self.unregister()

    # ------------------------------------------------------------------
    # Interactive shell
    # ------------------------------------------------------------------

    def run_interactive(self):
        """Simple command-line interface for chatting."""
        print("\nCommands:")
        print("  list              — show online peers")
        print("  send <user> <msg> — send message to peer")
        print("  quit              — exit\n")

        while True:
            try:
                line = input("{} > ".format(self.username)).strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not line:
                continue

            parts = line.split(None, 2)
            cmd = parts[0].lower()

            if cmd == "quit" or cmd == "exit":
                break

            elif cmd == "list":
                peers = self.list_peers()
                if not peers:
                    print("  (no peers online)")
                for p in peers:
                    marker = " <-- (you)" if p["username"] == self.username else ""
                    print("  {} at {}:{}{}".format(
                        p["username"], p["ip"], p["port"], marker))

            elif cmd == "send" and len(parts) >= 3:
                target = parts[1]
                text = parts[2]
                self.send_message(target, text)

            else:
                print("Unknown command. Use: list | send <user> <msg> | quit")

        self.stop()
