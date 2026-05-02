#
# Copyright (C) 2026 pdnguyen of HCMC University of Technology VNU-HCM.
# All rights reserved.
# This file is part of the CO3093/CO3094 course.
#
# AsynapRous release
#
# The authors hereby grant to Licensee personal permission to use
# and modify the Licensed Source Code for the sole purpose of studying
# while attending the course
#

"""
daemon.proxy
~~~~~~~~~~~~~~~~~

Simple reverse proxy server.

Routes incoming HTTP requests to backend services based on the ``Host``
header and a configuration-driven routing table.  Supports:

* Single-backend routing (direct ``proxy_pass``).
* Round-robin load balancing across multiple backends.

Non-blocking design: every accepted client connection is handled in its
own daemon thread so the accept loop is never blocked.
"""

import socket
import threading
from .response import Response
from .httpadapter import HttpAdapter
from .dictionary import CaseInsensitiveDict

# Round-robin counters per hostname: {hostname: current_index}
_rr_counters = {}
_rr_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Backend forwarding
# ---------------------------------------------------------------------------

def forward_request(host, port, request):
    """Open a TCP connection to *host*:*port*, send *request*, return the reply.

    :param host: Backend IP/hostname string.
    :param port: Backend port integer.
    :param request: Raw HTTP request string to forward.
    :returns: Raw HTTP response bytes from the backend.
    """
    backend = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        backend.connect((host, port))
        backend.sendall(request.encode("utf-8", errors="replace"))
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
        ).encode("utf-8")
    finally:
        backend.close()


# ---------------------------------------------------------------------------
# Load-balancing helpers
# ---------------------------------------------------------------------------

def _pick_round_robin(hostname, proxy_list):
    """Thread-safe round-robin selection from *proxy_list*.

    :param hostname: Hostname key used to track the counter.
    :param proxy_list: List of ``'host:port'`` strings.
    :returns: The selected ``'host:port'`` string.
    """
    with _rr_lock:
        idx = _rr_counters.get(hostname, 0)
        chosen = proxy_list[idx % len(proxy_list)]
        _rr_counters[hostname] = (idx + 1) % len(proxy_list)
    print("[Proxy] round-robin idx={} selected {}".format(idx, chosen))
    return chosen


# ---------------------------------------------------------------------------
# Route resolution
# ---------------------------------------------------------------------------

def resolve_routing_policy(hostname, routes):
    """Resolve the target backend ``(host, port)`` for *hostname*.

    Applies the ``dist_policy`` configured for the host block.
    Falls back to ``127.0.0.1:9000`` if no route matches.

    :param hostname: Value of the ``Host`` request header.
    :param routes: Routing table as returned by ``parse_virtual_hosts()``.
        Format: ``{hostname: (proxy_map, policy)}``.
    :returns: ``(proxy_host_str, proxy_port_int)`` tuple.
    """
    print("[Proxy] Resolving hostname: {}".format(hostname))

    entry = routes.get(hostname)
    if not entry:
        print("[Proxy] No route for '{}'; using default 127.0.0.1:9000".format(hostname))
        return "127.0.0.1", 9000

    proxy_map, policy = entry
    print("[Proxy] proxy_map={} policy={}".format(proxy_map, policy))

    if isinstance(proxy_map, list):
        if len(proxy_map) == 0:
            print("[Proxy] Empty proxy_map for {}".format(hostname))
            return "127.0.0.1", 9000
        elif len(proxy_map) == 1:
            target = proxy_map[0]
        else:
            # Apply distribution policy
            if policy == "round-robin":
                target = _pick_round_robin(hostname, proxy_map)
            else:
                # Default: first entry
                target = proxy_map[0]
    else:
        target = proxy_map

    proxy_host, proxy_port_str = target.split(":", 1)
    return proxy_host, int(proxy_port_str)


# ---------------------------------------------------------------------------
# Per-connection handler
# ---------------------------------------------------------------------------

def handle_client(ip, port, conn, addr, routes):
    """Handle one client connection: parse host, resolve backend, forward.

    :param ip: Proxy server IP string.
    :param port: Proxy server port integer.
    :param conn: Accepted client socket.
    :param addr: Client address tuple ``(ip, port)``.
    :param routes: Routing table dict.
    """
    try:
        request = conn.recv(4096).decode("utf-8", errors="replace")
    except Exception as e:
        print("[Proxy] recv error: {}".format(e))
        conn.close()
        return

    # Extract Host header
    hostname = None
    for line in request.splitlines():
        if line.lower().startswith("host:"):
            hostname = line.split(":", 1)[1].strip()
            break

    if not hostname:
        print("[Proxy] No Host header from {}; dropping".format(addr))
        conn.close()
        return

    print("[Proxy] {} Host: {}".format(addr, hostname))

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
        ).encode("utf-8")

    try:
        conn.sendall(response)
    except Exception as e:
        print("[Proxy] sendall error: {}".format(e))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Server loop
# ---------------------------------------------------------------------------

def run_proxy(ip, port, routes):
    """Bind, listen, and spawn one daemon thread per incoming connection.

    This implements **non-blocking multi-thread** handling at the proxy
    layer: the accept loop never blocks on slow clients.

    :param ip: IP address to bind.
    :param port: Port to listen on.
    :param routes: Routing table dict.
    """
    proxy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    proxy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        proxy.bind((ip, port))
        proxy.listen(50)
        print("[Proxy] Listening on {}:{}".format(ip, port))

        while True:
            conn, addr = proxy.accept()
            # Non-blocking: hand off to a daemon thread immediately
            t = threading.Thread(
                target=handle_client,
                args=(ip, port, conn, addr, routes),
                daemon=True,
            )
            t.start()

    except KeyboardInterrupt:
        print("[Proxy] Shutting down.")
    except socket.error as e:
        print("[Proxy] Socket error: {}".format(e))
    finally:
        proxy.close()


def create_proxy(ip, port, routes):
    """Entry point for launching the proxy server.

    :param ip: IP address to bind.
    :param port: Port to listen on.
    :param routes: Routing table as returned by ``parse_virtual_hosts()``.
    """
    run_proxy(ip, port, routes)
