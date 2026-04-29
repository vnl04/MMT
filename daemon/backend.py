#
# Copyright (C) 2026 pdnguyen of HCMC University of Technology VNU-HCM.
# All rights reserved.
# This file is part of the CO3093/CO3094 course.
#
# AsynapRous release
#

"""
daemon.backend
~~~~~~~~~~~~~~~~~

Backend server using socket + threading (or async coroutine).
Handles multiple clients concurrently.
"""

import socket
import threading
import asyncio
import inspect
import selectors

from .response import Response
from .httpadapter import HttpAdapter
from .dictionary import CaseInsensitiveDict

sel = selectors.DefaultSelector()

# Switch between: "threading", "callback", "coroutine"
mode_async = "threading"


def handle_client(ip, port, conn, addr, routes):
    """Spawn an HttpAdapter and let it handle the connection."""
    print("[Backend] Invoke handle_client accepted connection from {}".format(addr))
    daemon = HttpAdapter(ip, port, conn, addr, routes)
    daemon.handle_client(conn, addr, routes)


def handle_client_callback(server, ip, port, conn, addr, routes):
    """Callback-style handler used with selectors."""
    print("[Backend] Invoke handle_client_callback accepted connection from {}".format(addr))
    daemon = HttpAdapter(ip, port, conn, addr, routes)
    daemon.handle_client(conn, addr, routes)


async def handle_client_coroutine(reader, writer):
    """Async coroutine handler — reads, processes, writes, closes."""
    addr = writer.get_extra_info("peername")
    print("[Backend] Invoke handle_client_coroutine accepted connection from {}".format(addr))
    daemon = HttpAdapter(None, None, None, addr, {})
    await daemon.handle_client_coroutine(reader, writer)


async def async_server(ip="0.0.0.0", port=7000, routes={}):
    print("[Backend] async_server **ASYNC** listening on port {}".format(port))
    if routes:
        print("[Backend] route settings")
        for key, value in routes.items():
            tag = "**ASYNC** " if inspect.iscoroutinefunction(value) else ""
            print("   + ('{}', '{}'): {}{}".format(key[0], key[1], tag, value))

    srv = await asyncio.start_server(handle_client_coroutine, ip, port)
    async with srv:
        await srv.serve_forever()


def run_backend(ip, port, routes):
    """Start the server loop. Mode is controlled by global mode_async."""
    global mode_async

    print("[Backend] run_backend with routes={}".format(routes))

    if mode_async == "coroutine":
        asyncio.run(async_server(ip, port, routes))
        return

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server.bind((ip, port))
        server.listen(50)

        print("[Backend] Listening on port {}".format(port))
        if routes:
            print("[Backend] route settings")
            for key, value in routes.items():
                tag = "**ASYNC** " if inspect.iscoroutinefunction(value) else ""
                print("   + ('{}', '{}'): {}{}".format(key[0], key[1], tag, value))

        if mode_async == "callback":
            server.setblocking(False)
            sel.register(server, selectors.EVENT_READ, (handle_client_callback, ip, port, routes))

        while True:
            if mode_async == "callback":
                events = sel.select(timeout=None)
                for key, mask in events:
                    if key.fileobj is server:
                        conn, addr = server.accept()
                        callback, _ip, _port, _routes = key.data
                        t = threading.Thread(
                            target=callback,
                            args=(server, _ip, _port, conn, addr, _routes),
                            daemon=True
                        )
                        t.start()
                    else:
                        callback, _ip, _port, _routes = key.data
                        conn = key.fileobj
                        addr = conn.getpeername()
                        callback(server, _ip, _port, conn, addr, _routes)
            else:
                # Default: one thread per connection
                conn, addr = server.accept()
                t = threading.Thread(
                    target=handle_client,
                    args=(ip, port, conn, addr, routes),
                    daemon=True
                )
                t.start()

    except socket.error as e:
        print("Socket error: {}".format(e))
    finally:
        server.close()


def create_backend(ip, port, routes={}):
    """Entry point: create and run the backend server."""
    run_backend(ip, port, routes)
