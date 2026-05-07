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

HTTP adapter: read request, dispatch route hooks, build response.

FIX (Bug 7): ``handle_client_coroutine`` passes ``self.routes`` to
``req.prepare()`` so asyncio mode resolves hooks correctly.

FIX (Bug 2): ``handle_client(..., raw=...)`` allows the backend to inject
already-read bytes (optional); default behaviour unchanged.
"""

from .request import Request
from .response import Response

import asyncio
import base64
import inspect


class HttpAdapter:

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

    def handle_client(self, conn, addr, routes, raw=None):
        self.conn = conn
        self.connaddr = addr

        req = self.request
        resp = self.response

        try:
            if raw is not None:
                msg = raw if isinstance(raw, str) else raw.decode("utf-8", errors="replace")
            else:
                msg = conn.recv(4096).decode("utf-8", errors="replace")
        except Exception as e:
            print("[HttpAdapter] recv error: {}".format(e))
            conn.close()
            return

        req.prepare(msg, routes)
        print("[HttpAdapter] handle_client from {}".format(addr))

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

    async def handle_client_coroutine(self, reader, writer):
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

        if req.method == "OPTIONS":
            writer.write(resp.build_cors_preflight())
            await writer.drain()
            writer.close()
            return

        if req.hook:
            response = await self._dispatch_hook_async(req, resp)
        else:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, resp.build_response, req)

        writer.write(response)
        await writer.drain()
        writer.close()

    def _dispatch_hook(self, req, resp):
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
        extra_headers = None
        if isinstance(result, tuple) and len(result) == 2:
            content, extra_headers = result
        else:
            content = result

        if not isinstance(content, bytes):
            content = str(content).encode("utf-8")

        return content, extra_headers

    def extract_cookies(self, req, resp=None):
        cookies = {}
        cookie_str = req.headers.get("cookie", "") if hasattr(req.headers, "get") else ""
        if cookie_str:
            for pair in cookie_str.split(";"):
                pair = pair.strip()
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    cookies[key.strip()] = value.strip()
        return cookies

    def add_headers(self, request):
        pass

    def build_proxy_headers(self, proxy):
        headers = {}
        username, password = ("user1", "password")
        if username:
            token = base64.b64encode(
                "{}:{}".format(username, password).encode()
            ).decode()
            headers["Proxy-Authorization"] = "Basic {}".format(token)
        return headers
