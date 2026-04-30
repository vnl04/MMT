#
# Copyright (C) 2026 pdnguyen of HCMC University of Technology VNU-HCM.
# All rights reserved.
# This file is part of the CO3093/CO3094 course.
#
# AsynapRous release
#

"""
daemon.httpadapter
~~~~~~~~~~~~~~~~~

HTTP adapter that reads requests, dispatches to route handlers,
and builds/sends back responses.
"""

from .request import Request
from .response import Response
from .dictionary import CaseInsensitiveDict

import asyncio
import inspect

class HttpAdapter:
    """Manages a single client connection end-to-end."""

    __attrs__ = [
        "ip", "port", "conn", "connaddr", "routes", "request", "response",
    ]

    def __init__(self, ip, port, conn, connaddr, routes):
        self.ip = ip
        self.port = port
        self.conn = conn
        self.connaddr = connaddr
        self.routes = routes if routes else {}
        self.request = Request()
        self.response = Response()

    def handle_client(self, conn, addr, routes):
        """Read request, call route hook if any, build and send response."""
        self.conn = conn
        self.connaddr = addr

        req = self.request
        resp = self.response

        try:
            msg = conn.recv(4096).decode('utf-8', errors='replace')
        except Exception as e:
            print("[HttpAdapter] recv error: {}".format(e))
            conn.close()
            return

        req.prepare(msg, routes)
        print("[HttpAdapter] Invoke handle_client connection {}".format(addr))

        # Handle CORS preflight (OPTIONS)
        if req.method == "OPTIONS":
            try:
                conn.sendall(resp.build_cors_preflight())
            except Exception:
                pass
            conn.close()
            return

        response = b""

        if req.hook:
            print("[HttpAdapter] Dispatching to hook: {}".format(req.hook))
            try:
                if inspect.iscoroutinefunction(req.hook):
                    loop = asyncio.new_event_loop()
                    result = loop.run_until_complete(req.hook(req.headers, req.body))
                    loop.close()
                else:
                    result = req.hook(req.headers, req.body)

                # Hook may return bytes OR (bytes, extra_headers_dict)
                extra_headers = None
                if isinstance(result, tuple) and len(result) == 2:
                    content, extra_headers = result
                else:
                    content = result

                if isinstance(content, bytes):
                    response = resp.build_json_response(content, extra_headers)
                else:
                    response = resp.build_json_response(
                        str(content).encode('utf-8'), extra_headers
                    )

            except Exception as e:
                print("[HttpAdapter] hook error: {}".format(e))
                response = resp.build_notfound()
        else:
            response = resp.build_response(req)

        try:
            conn.sendall(response)
        except Exception as e:
            print("[HttpAdapter] sendall error: {}".format(e))
        finally:
            conn.close()

    async def handle_client_coroutine(self, reader, writer):
        """Async version of handle_client using StreamReader/StreamWriter."""
        req = self.request
        resp = self.response

        addr = writer.get_extra_info("peername")
        print("[HttpAdapter] Invoke handle_client_coroutine connection {}".format(addr))

        try:
            msg = await reader.read(4096)
            req.prepare(msg.decode('utf-8', errors='replace'), routes=self.routes)
        except Exception as e:
            print("[HttpAdapter] async read error: {}".format(e))
            writer.close()
            return

        # Handle CORS preflight
        if req.method == "OPTIONS":
            writer.write(resp.build_cors_preflight())
            await writer.drain()
            writer.close()
            return

        response = b""

        if req.hook:
            try:
                if inspect.iscoroutinefunction(req.hook):
                    result = await req.hook(req.headers, req.body)
                else:
                    result = req.hook(req.headers, req.body)

                # Hook may return bytes OR (bytes, extra_headers_dict)
                extra_headers = None
                if isinstance(result, tuple) and len(result) == 2:
                    content, extra_headers = result
                else:
                    content = result

                if isinstance(content, bytes):
                    response = resp.build_json_response(content, extra_headers)
                else:
                    response = resp.build_json_response(
                        str(content).encode('utf-8'), extra_headers
                    )
            except Exception as e:
                print("[HttpAdapter] async hook error: {}".format(e))
                response = resp.build_notfound()
        else:
            response = resp.build_response(req)

        writer.write(response)
        await writer.drain()
        writer.close()

    def extract_cookies(self, req, resp=None):
        """Parse Cookie header into a dict."""
        cookies = {}
        cookie_str = req.headers.get('cookie', '')
        if cookie_str:
            for pair in cookie_str.split(';'):
                pair = pair.strip()
                if '=' in pair:
                    key, value = pair.split('=', 1)
                    cookies[key.strip()] = value.strip()
        return cookies

    def build_response(self, req, resp=None):
        """Wrapper that delegates to Response.build_response."""
        response = Response()
        response.encoding = 'utf-8'
        response.url = req.url or req.path
        response.cookies = self.extract_cookies(req)
        response.request = req
        response.connection = self
        return response

    def build_json_response(self, req, resp=None):
        """Wrapper for JSON responses."""
        response = Response(req)
        response.raw = resp
        response.url = req.url or req.path
        response.request = req
        response.connection = self
        return response

    def add_headers(self, request):
        pass

    def build_proxy_headers(self, proxy):
        headers = {}
        username, password = ("user1", "password")
        if username:
            import base64
            token = base64.b64encode("{}:{}".format(username, password).encode()).decode()
            headers["Proxy-Authorization"] = "Basic {}".format(token)
        return headers
