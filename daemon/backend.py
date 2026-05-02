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
daemon.backend
~~~~~~~~~~~~~~~~~

Backend server using socket + threading (or async coroutine).
Handles multiple clients concurrently via three non-blocking mechanisms:
  - threading  : one thread per connection (default)
  - callback   : event-driven using selectors (non-blocking I/O)
  - coroutine  : asyncio StreamReader/StreamWriter

Change global ``mode_async`` to switch between mechanisms.
"""

import socket
import threading
import asyncio
import inspect
import selectors

from .response import Response
from .httpadapter import HttpAdapter
from .dictionary import CaseInsensitiveDict

# Switch between: "threading", "callback", "coroutine"
mode_async = "threading"


# ---------------------------------------------------------------------------
# Per-connection handler — used by all three modes
# ---------------------------------------------------------------------------

def handle_client(ip, port, conn, addr, routes):
    """Spawn an HttpAdapter and let it handle one connection (threading mode)."""
    print("[Backend] handle_client accepted connection from {}".format(addr))
    daemon = HttpAdapter(ip, port, conn, addr, routes)
    daemon.handle_client(conn, addr, routes)


# ---------------------------------------------------------------------------
# Callback / selector mode
# ---------------------------------------------------------------------------

def _accept_callback(server_sock, ip, port, routes, sel):
    """
    Called by the selector loop when the server socket is readable.
    Accepts one connection and spawns a daemon thread to handle it
    (so the selector loop is never blocked by slow clients).
    """
    try:
        conn, addr = server_sock.accept()
    except BlockingIOError:
        return
    print("[Backend] [callback] accepted connection from {}".format(addr))
    t = threading.Thread(
        target=handle_client,
        args=(ip, port, conn, addr, routes),
        daemon=True,
    )
    t.start()


# ---------------------------------------------------------------------------
# Coroutine / asyncio mode
# ---------------------------------------------------------------------------

async def _handle_client_coroutine(reader, writer):
    """Async coroutine handler — reads, processes, writes, closes."""
    addr = writer.get_extra_info("peername")
    print("[Backend] [coroutine] accepted connection from {}".format(addr))
    daemon = HttpAdapter(None, None, None, addr, {})
    await daemon.handle_client_coroutine(reader, writer)


async def _async_server(ip, port, routes):
    """Start an asyncio server. routes are stored on the daemon module-level
    so coroutine handlers can reach them."""
    # Patch routes into the coroutine closure via a wrapper
    async def _handler(reader, writer):
        addr = writer.get_extra_info("peername")
        print("[Backend] [coroutine] accepted connection from {}".format(addr))
        daemon = HttpAdapter(None, None, None, addr, routes)
        await daemon.handle_client_coroutine(reader, writer)

    print("[Backend] [coroutine] listening on {}:{}".format(ip, port))
    _log_routes(routes)
    srv = await asyncio.start_server(_handler, ip, port)
    async with srv:
        await srv.serve_forever()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log_routes(routes):
    if routes:
        print("[Backend] route settings:")
        for key, value in routes.items():
            tag = "**ASYNC** " if inspect.iscoroutinefunction(value) else ""
            print("   + ('{}', '{}'): {}{}".format(key[0], key[1], tag, value))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_backend(ip, port, routes):
    """
    Start the server loop.

    Selects the concurrency mechanism via the global ``mode_async``:

    * ``"threading"``  — one OS thread per accepted connection.
    * ``"callback"``   — single-threaded selector loop; each accepted
                         connection is handed off to a daemon thread so
                         the selector is never blocked.
    * ``"coroutine"``  — asyncio event loop with StreamReader/StreamWriter.
    """
    global mode_async

    print("[Backend] run_backend mode={} routes={}".format(mode_async, list(routes.keys())))

    # ---- coroutine mode ----
    if mode_async == "coroutine":
        asyncio.run(_async_server(ip, port, routes))
        return

    # ---- threading & callback modes share the same socket setup ----
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server.bind((ip, port))
        server.listen(50)
        print("[Backend] Listening on {}:{}".format(ip, port))
        _log_routes(routes)

        if mode_async == "callback":
            # Put the server socket in non-blocking mode and register with selector
            server.setblocking(False)
            sel = selectors.DefaultSelector()
            sel.register(server, selectors.EVENT_READ)

            print("[Backend] [callback] selector loop started")
            while True:
                events = sel.select(timeout=1.0)
                for key, mask in events:
                    if key.fileobj is server and (mask & selectors.EVENT_READ):
                        _accept_callback(server, ip, port, routes, sel)

        else:
            # Default: one thread per connection (threading mode)
            print("[Backend] [threading] thread-per-connection loop started")
            while True:
                conn, addr = server.accept()
                t = threading.Thread(
                    target=handle_client,
                    args=(ip, port, conn, addr, routes),
                    daemon=True,
                )
                t.start()

    except KeyboardInterrupt:
        print("[Backend] Shutting down.")
    except socket.error as e:
        print("[Backend] Socket error: {}".format(e))
    finally:
        server.close()


def create_backend(ip, port, routes={}):
    """Entry point: create and run the backend server."""
    run_backend(ip, port, routes)
