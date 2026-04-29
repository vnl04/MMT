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

This module provides a Request object to manage and persist 
request settings (cookies, auth, proxies).
"""
from .dictionary import CaseInsensitiveDict

class Request():
    """The fully mutable Request object for parsing incoming HTTP messages."""

    __attrs__ = [
        "method",
        "url",
        "headers",
        "body",
        "_raw_headers",
        "_raw_body",
        "reason",
        "cookies",
        "body",
        "routes",
        "hook",
    ]

    def __init__(self):
        self.method = None
        self.url = None
        self.headers = CaseInsensitiveDict()
        self.path = None
        self.version = None
        self.cookies = CaseInsensitiveDict()
        self.body = None
        self._raw_headers = None
        self._raw_body = None
        self.routes = {}
        self.hook = None

    def extract_request_line(self, request):
        try:
            lines = request.splitlines()
            first_line = lines[0]
            parts = first_line.split()
            if len(parts) < 3:
                return None, None, None
            method, path, version = parts[0], parts[1], parts[2]
            if path == '/':
                path = '/index.html'
        except Exception:
            return None, None, None
        return method, path, version

    def prepare_headers(self, request):
        """Parses raw HTTP headers into a dict."""
        lines = request.split('\r\n')
        headers = CaseInsensitiveDict()
        for line in lines[1:]:
            if ': ' in line:
                key, val = line.split(': ', 1)
                headers[key] = val
        return headers

    def fetch_headers_body(self, request):
        """Splits raw HTTP request into header section and body."""
        parts = request.split("\r\n\r\n", 1)
        _headers = parts[0]
        _body = parts[1] if len(parts) > 1 else ""
        return _headers, _body

    def prepare(self, request, routes=None):
        """Parses the full HTTP request message."""
        print("[Request] prepare request msg {}".format(request[:100] if request else ""))

        self.method, self.path, self.version = self.extract_request_line(request)
        print("[Request] {} path {} version {}".format(self.method, self.path, self.version))

        # Split headers and body
        self._raw_headers, self._raw_body = self.fetch_headers_body(request)
        self.headers = self.prepare_headers(self._raw_headers)
        self.body = self._raw_body

        # Hook routing setup
        if routes and routes != {}:
            self.routes = routes
            print("[Request] Routing METHOD {} path {}".format(self.method, self.path))
            self.hook = routes.get((self.method, self.path))
            print("[Request] Hook found: {}".format(self.hook))

        # Parse cookies from header
        cookie_str = self.headers.get('cookie', '')
        if cookie_str:
            self.cookies = self.prepare_cookies(cookie_str)

        return

    def prepare_body(self, data, files=None, json=None):
        self.body = data
        self.prepare_content_length(self.body)
        return

    def prepare_content_length(self, body):
        if body:
            self.headers["Content-Length"] = str(len(body))
        else:
            self.headers["Content-Length"] = "0"
        return

    def prepare_auth(self, auth, url=""):
        if auth:
            import base64
            username, password = auth
            token = base64.b64encode("{}:{}".format(username, password).encode()).decode()
            self.headers["Authorization"] = "Basic {}".format(token)
        return

    def prepare_cookies(self, cookies):
        """Parse cookie string into a CaseInsensitiveDict."""
        cookie_dict = CaseInsensitiveDict()
        if isinstance(cookies, str):
            for pair in cookies.split(';'):
                pair = pair.strip()
                if '=' in pair:
                    k, v = pair.split('=', 1)
                    cookie_dict[k.strip()] = v.strip()
        return cookie_dict
