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
daemon.httpadapter
~~~~~~~~~~~~~~~~~

HTTP adapter: reads a raw request, parses it, dispatches to route hooks
(RESTful API handlers), builds the response, and sends it back.

Supports:
  - Synchronous and async (coroutine) route hooks.
  - CORS preflight (OPTIONS).
  - RFC 7235 / RFC 2617 Basic Auth challenge via ``WWW-Authenticate``.
  - RFC 6265 ``Set-Cookie`` forwarded from hook extra-headers.
  - Hook returning ``(bytes, extra_headers_dict)`` or plain ``bytes``.
"""

from .request import Request
from .response import Response
from .dictionary import CaseInsensitiveDict

import asyncio
import base64
import inspect


class HttpAdapter:
    """Manages a single client connection end-to-end.

    :param ip: Server IP address string.
    :param port: Server port integer.
    :param conn: Active client socket.
    :param connaddr: ``(ip, port)`` tuple of the remote client.
    :param routes: Route mapping ``{(method, path): handler}``.
    """

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

    # ------------------------------------------------------------------
    # Synchronous handler
    # ------------------------------------------------------------------

    def handle_client(self, conn, addr, routes):
        """Read request, dispatch to hook or static file, send response.

        :param conn: Client socket.
        :param addr: Client address tuple.
        :param routes: Route mapping dict.
        """
        self.conn = conn
        self.connaddr = addr

        req = self.request
        resp = self.response

        # Read raw request
        try:
            msg = conn.recv(4096).decode("utf-8", errors="replace")
        except Exception as e:
            print("[HttpAdapter] recv error: {}".format(e))
            conn.close()
            return

        req.prepare(msg, routes)
        print("[HttpAdapter] handle_client from {}".format(addr))

        # CORS preflight
        if req.method == "OPTIONS":
            try:
                conn.sendall(resp.build_cors_preflight())
            except Exception:
                pass
            conn.close()
            return

        response = b""

        if req.hook:
            response = self._dispatch_hook(req, resp)
        else:
            response = resp.build_response(req)

        try:
            conn.sendall(response)
        except Exception as e:
            print("[HttpAdapter] sendall error: {}".format(e))
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Async (coroutine) handler
    # ------------------------------------------------------------------

    async def handle_client_coroutine(self, reader, writer):
        """Async version of handle_client using StreamReader / StreamWriter.

        :param reader: asyncio StreamReader.
        :param writer: asyncio StreamWriter.
        """
        req = self.request
        resp = self.response

        addr = writer.get_extra_info("peername")
        print("[HttpAdapter] handle_client_coroutine from {}".format(addr))

        try:
            msg = await reader.read(4096)
            req.prepare(msg.decode("utf-8", errors="replace"), routes=self.routes)
        except Exception as e:
            print("[HttpAdapter] async read error: {}".format(e))
            writer.close()
            return

        # CORS preflight
        if req.method == "OPTIONS":
            writer.write(resp.build_cors_preflight())
            await writer.drain()
            writer.close()
            return

        if req.hook:
            response = await self._dispatch_hook_async(req, resp)
        else:
            response = resp.build_response(req)

        writer.write(response)
        await writer.drain()
        writer.close()

    # ------------------------------------------------------------------
    # Hook dispatch helpers
    # ------------------------------------------------------------------

    def _dispatch_hook(self, req, resp):
        """Call a synchronous (or async) route hook and build the HTTP response.

        Hook functions may return:
          * ``bytes``                        — plain body
          * ``(bytes, dict)``                — body + extra headers (e.g. Set-Cookie)

        :param req: Parsed :class:`Request`.
        :param resp: :class:`Response` instance.
        :returns: Complete encoded HTTP response bytes.
        """
        print("[HttpAdapter] Dispatching hook: {}".format(req.hook))
        try:
            if inspect.iscoroutinefunction(req.hook):
                loop = asyncio.new_event_loop()
                result = loop.run_until_complete(req.hook(req.headers, req.body))
                loop.close()
            else:
                result = req.hook(req.headers, req.body)

            content, extra_headers = self._unpack_hook_result(result)
            return resp.build_json_response(content, extra_headers)

        except Exception as e:
            print("[HttpAdapter] hook error: {}".format(e))
            return resp.build_notfound()

    async def _dispatch_hook_async(self, req, resp):
        """Async version of :meth:`_dispatch_hook`.

        :param req: Parsed :class:`Request`.
        :param resp: :class:`Response` instance.
        :returns: Complete encoded HTTP response bytes.
        """
        print("[HttpAdapter] Async dispatching hook: {}".format(req.hook))
        try:
            if inspect.iscoroutinefunction(req.hook):
                result = await req.hook(req.headers, req.body)
            else:
                result = req.hook(req.headers, req.body)

            content, extra_headers = self._unpack_hook_result(result)
            return resp.build_json_response(content, extra_headers)

        except Exception as e:
            print("[HttpAdapter] async hook error: {}".format(e))
            return resp.build_notfound()

    @staticmethod
    def _unpack_hook_result(result):
        """Unpack hook return value into ``(content_bytes, extra_headers)``.

        :param result: Hook return value — ``bytes`` or ``(bytes, dict)``.
        :returns: ``(bytes, dict | None)`` tuple.
        """
        extra_headers = None
        if isinstance(result, tuple) and len(result) == 2:
            content, extra_headers = result
        else:
            content = result

        if not isinstance(content, bytes):
            content = str(content).encode("utf-8")

        return content, extra_headers

    # ------------------------------------------------------------------
    # Cookie helpers
    # ------------------------------------------------------------------

    def extract_cookies(self, req, resp=None):
        """Parse the ``Cookie`` header from *req* into a plain dict.

        :param req: :class:`Request` object.
        :returns: ``{name: value}`` dict.
        """
        cookies = {}
        cookie_str = req.headers.get("cookie", "") if hasattr(req.headers, "get") else ""
        if cookie_str:
            for pair in cookie_str.split(";"):
                pair = pair.strip()
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    cookies[key.strip()] = value.strip()
        return cookies

    # ------------------------------------------------------------------
    # Proxy support
    # ------------------------------------------------------------------

    def add_headers(self, request):
        """Hook point for subclasses to inject custom request headers.

        :param request: :class:`Request` object.
        """
        pass

    def build_proxy_headers(self, proxy):
        """Return a dict of headers to add when forwarding through *proxy*.

        Builds a ``Proxy-Authorization: Basic <b64>`` header from
        configured credentials.

        :param proxy: Proxy URL string.
        :returns: ``dict`` of header name → value pairs.
        """
        headers = {}
        # TODO: load real credentials from config / environment
        username, password = ("user1", "password")
        if username:
            token = base64.b64encode(
                "{}:{}".format(username, password).encode()
            ).decode()
            headers["Proxy-Authorization"] = "Basic {}".format(token)
        return headers
