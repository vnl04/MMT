#
# Copyright (C) 2026 pdnguyen of HCMC University of Technology VNU-HCM.
# All rights reserved.
# This file is part of the CO3093/CO3094 course.
#
# AsynapRous release
#

"""
daemon.request
~~~~~~~~~~~~~~~~~

Parses raw HTTP/1.1 request messages into a structured :class:`Request`
object consumed by :class:`HttpAdapter` and route handlers.

FIX (Bug 1): Route lookup normalises trailing slashes so ``/login`` and
``/login/`` resolve to the same handler. Query strings are stripped from the
path before routing.

FIX (Bug 2): The raw query string (everything after ``?``) is preserved
in ``self.query_string`` and injected into the parsed headers as
``X-Query-String`` so handlers such as ``GET /messages`` can still read
``?channel=general`` even though routing strips the query component.
"""

import base64
from .dictionary import CaseInsensitiveDict


class Request:
    """Fully parsed HTTP request."""

    __attrs__ = [
        "method",
        "url",
        "headers",
        "body",
        "_raw_headers",
        "_raw_body",
        "version",
        "reason",
        "cookies",
        "auth",
        "routes",
        "hook",
        "query_string",
    ]

    def __init__(self):
        self.method = None
        self.url = None
        self.headers = CaseInsensitiveDict()
        self.path = None
        self.version = None
        self.cookies = CaseInsensitiveDict()
        self.auth = None
        self.body = None
        self._raw_headers = None
        self._raw_body = None
        self.routes = {}
        self.hook = None
        self.query_string = ""

    def extract_request_line(self, request):
        """Parse request line and preserve raw query string."""
        try:
            lines = request.splitlines()
            first_line = lines[0]
            parts = first_line.split()
            if len(parts) < 3:
                return None, None, None
            method, path, version = parts[0], parts[1], parts[2]
            if "?" in path:
                path, qs = path.split("?", 1)
                self.query_string = qs
            else:
                self.query_string = ""
            if path == "/":
                path = "/index.html"
        except Exception:
            return None, None, None
        return method, path, version

    def prepare_headers(self, header_section):
        headers = CaseInsensitiveDict()
        lines = header_section.split("\r\n")
        for line in lines[1:]:
            if ": " in line:
                key, val = line.split(": ", 1)
                headers[key.strip()] = val.strip()
        return headers

    def fetch_headers_body(self, request):
        parts = request.split("\r\n\r\n", 1)
        _headers = parts[0]
        _body = parts[1] if len(parts) > 1 else ""
        return _headers, _body

    def prepare_cookies(self, cookie_str):
        cookie_dict = CaseInsensitiveDict()
        if isinstance(cookie_str, str):
            for pair in cookie_str.split(";"):
                pair = pair.strip()
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    cookie_dict[k.strip()] = v.strip()
        return cookie_dict

    def prepare_auth(self, auth_header, url=""):
        if not auth_header:
            return
        try:
            scheme, _, credentials = auth_header.partition(" ")
            if scheme.lower() == "basic":
                decoded = base64.b64decode(credentials).decode("utf-8", errors="replace")
                username, _, password = decoded.partition(":")
                self.auth = (username, password)
                print("[Request] Basic auth for user: {}".format(username))
        except Exception as e:
            print("[Request] Auth parse error: {}".format(e))

    def prepare_body(self, data, files=None, json=None):
        self.body = data
        self.prepare_content_length(self.body)

    def prepare_content_length(self, body):
        if body:
            length = len(body.encode("utf-8") if isinstance(body, str) else body)
            self.headers["Content-Length"] = str(length)
        else:
            self.headers["Content-Length"] = "0"

    def _lookup_hook(self, routes, method, path):
        hook = routes.get((method, path))
        if hook:
            return hook
        if path.endswith("/") and len(path) > 1:
            hook = routes.get((method, path.rstrip("/")))
            if hook:
                return hook
        hook = routes.get((method, path + "/"))
        if hook:
            return hook
        return None

    def prepare(self, request, routes=None):
        if not request:
            return

        preview = request[:120].replace("\r\n", " | ")
        print("[Request] prepare: {}".format(preview))

        self.method, self.path, self.version = self.extract_request_line(request)
        print("[Request] {} {} {}".format(self.method, self.path, self.version))

        self._raw_headers, self._raw_body = self.fetch_headers_body(request)
        self.headers = self.prepare_headers(self._raw_headers)
        self.body = self._raw_body

        if self.query_string:
            self.headers["x-query-string"] = self.query_string

        cookie_str = self.headers.get("cookie", "")
        if cookie_str:
            self.cookies = self.prepare_cookies(cookie_str)

        auth_header = self.headers.get("authorization", "")
        if auth_header:
            self.prepare_auth(auth_header)

        if routes:
            self.routes = routes
            print("[Request] Routing {} {}".format(self.method, self.path))
            self.hook = self._lookup_hook(routes, self.method, self.path)
            print("[Request] Hook found: {}".format(self.hook))
