#
# Copyright (C) 2026 pdnguyen of HCMC University of Technology VNU-HCM.
# All rights reserved.
# This file is part of the CO3093/CO3094 course.
#
# AsynapRous release
#

"""
daemon.proxy
~~~~~~~~~~~~~~~~~

Simple reverse proxy server. Routes requests by Host header to configured backends.
Supports round-robin load balancing across multiple backend servers.
"""

import socket
import threading
from .response import Response
from .httpadapter import HttpAdapter
from .dictionary import CaseInsensitiveDict

# Round-robin counters per hostname: {hostname: current_index}
_rr_counters = {}
_rr_lock = threading.Lock()


def forward_request(host, port, request):
    """Connect to backend, send request, collect and return response bytes."""
    backend = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        backend.connect((host, port))
        backend.sendall(request.encode('utf-8', errors='replace'))
        response = b""
        while True:
            chunk = backend.recv(4096)
            if not chunk:
                break
            response += chunk
        return response
    except socket.error as e:
        print("[Proxy] forward_request socket error: {}".format(e))
        return (
            "HTTP/1.1 502 Bad Gateway\r\n"
            "Content-Type: text/plain\r\n"
            "Content-Length: 11\r\n"
            "Connection: close\r\n"
            "\r\n"
            "Bad Gateway"
        ).encode('utf-8')
    finally:
        backend.close()


def _pick_round_robin(hostname, proxy_list):
    """
    Pick next backend from proxy_list using round-robin.
    Thread-safe via _rr_lock.
    """
    with _rr_lock:
        idx = _rr_counters.get(hostname, 0)
        chosen = proxy_list[idx % len(proxy_list)]
        _rr_counters[hostname] = (idx + 1) % len(proxy_list)
    print("[Proxy] round-robin index={} selected {}".format(idx, chosen))
    return chosen


def resolve_routing_policy(hostname, routes):
    """
    Look up hostname in routes dict and return (proxy_host, proxy_port).
    Applies the configured dist_policy (round-robin, etc.).
    Falls back to 127.0.0.1:9000 if nothing matches.
    """
    print("[Proxy] Resolving hostname: {}".format(hostname))

    entry = routes.get(hostname)
    if not entry:
        print("[Proxy] No route for {}; using default".format(hostname))
        return '127.0.0.1', 9000

    proxy_map, policy = entry
    print("[Proxy] proxy_map={} policy={}".format(proxy_map, policy))

    if isinstance(proxy_map, list):
        if len(proxy_map) == 0:
            print("[Proxy] Empty proxy_map for {}".format(hostname))
            return '127.0.0.1', 9000
        elif len(proxy_map) == 1:
            target = proxy_map[0]
        else:
            # Apply round-robin policy
            if policy == 'round-robin':
                target = _pick_round_robin(hostname, proxy_map)
            else:
                # default: just take first
                target = proxy_map[0]
    else:
        target = proxy_map

    proxy_host, proxy_port = target.split(':', 1)
    return proxy_host, int(proxy_port)


def handle_client(ip, port, conn, addr, routes):
    """Read client request, resolve backend, forward, send reply back."""
    try:
        request = conn.recv(4096).decode('utf-8', errors='replace')
    except Exception as e:
        print("[Proxy] recv error: {}".format(e))
        conn.close()
        return

    hostname = None
    for line in request.splitlines():
        if line.lower().startswith('host:'):
            hostname = line.split(':', 1)[1].strip()
            break

    if not hostname:
        print("[Proxy] No Host header found, dropping connection")
        conn.close()
        return

    print("[Proxy] {} at Host: {}".format(addr, hostname))

    resolved_host, resolved_port = resolve_routing_policy(hostname, routes)

    if resolved_host:
        print("[Proxy] Forwarding {} -> {}:{}".format(hostname, resolved_host, resolved_port))
        response = forward_request(resolved_host, resolved_port, request)
    else:
        response = (
            "HTTP/1.1 404 Not Found\r\n"
            "Content-Type: text/plain\r\n"
            "Content-Length: 13\r\n"
            "Connection: close\r\n"
            "\r\n"
            "404 Not Found"
        ).encode('utf-8')

    try:
        conn.sendall(response)
    except Exception as e:
        print("[Proxy] sendall error: {}".format(e))
    finally:
        conn.close()


def run_proxy(ip, port, routes):
    """Bind, listen, and spawn a thread per incoming connection."""
    proxy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    proxy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        proxy.bind((ip, port))
        proxy.listen(50)
        print("[Proxy] Listening on IP {} port {}".format(ip, port))

        while True:
            conn, addr = proxy.accept()
            t = threading.Thread(
                target=handle_client,
                args=(ip, port, conn, addr, routes),
                daemon=True
            )
            t.start()

    except socket.error as e:
        print("[Proxy] Socket error: {}".format(e))
    finally:
        proxy.close()


def create_proxy(ip, port, routes):
    """Entry point for launching the proxy server."""
    run_proxy(ip, port, routes)
