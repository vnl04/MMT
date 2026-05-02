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
daemon.request
~~~~~~~~~~~~~~~~~

Parses raw HTTP/1.1 request messages into a structured :class:`Request`
object consumed by :class:`HttpAdapter` and route handlers.

Parsing covers:
  - Request line: method, path, HTTP version.
  - Headers: case-insensitive dict (RFC 7230).
  - Body: raw bytes following the blank line separator.
  - Cookies: parsed from the ``Cookie`` header (RFC 6265).
  - Authorization: Basic auth decoded from ``Authorization`` header (RFC 2617).
  - Route hooks: looked up from the provided routes mapping.
"""

import base64
from .dictionary import CaseInsensitiveDict


class Request:
    """Fully parsed HTTP request.

    Instances are produced by calling :meth:`prepare` on a raw request string
    received from a client socket.

    Usage::

      >>> req = Request()
      >>> req.prepare(raw_http_string, routes=app.routes)
      >>> req.method   # 'GET', 'POST', etc.
      >>> req.path     # '/index.html'
      >>> req.headers  # CaseInsensitiveDict
      >>> req.body     # str body payload
      >>> req.hook     # callable handler or None
    """

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
    ]

    def __init__(self):
        #: HTTP method string, e.g. ``'GET'``.
        self.method = None
        #: Full URL (unused in server mode; populated if available).
        self.url = None
        #: Case-insensitive dict of request headers.
        self.headers = CaseInsensitiveDict()
        #: URL path, e.g. ``'/index.html'``.
        self.path = None
        #: HTTP version string, e.g. ``'HTTP/1.1'``.
        self.version = None
        #: Parsed cookies as a :class:`CaseInsensitiveDict`.
        self.cookies = CaseInsensitiveDict()
        #: Decoded ``(username, password)`` tuple if Basic auth present.
        self.auth = None
        #: Request body as a string.
        self.body = None
        #: Raw header section string.
        self._raw_headers = None
        #: Raw body section string.
        self._raw_body = None
        #: Route mapping ``{(method, path): handler}``.
        self.routes = {}
        #: Matched handler callable, or ``None``.
        self.hook = None

    # ------------------------------------------------------------------
    # Request-line parsing
    # ------------------------------------------------------------------

    def extract_request_line(self, request):
        """Parse the first line of an HTTP request.

        Normalises ``/`` to ``/index.html``.

        :param request: Raw request string.
        :returns: ``(method, path, version)`` triple, or ``(None, None, None)``
            on parse failure.
        """
        try:
            lines = request.splitlines()
            first_line = lines[0]
            parts = first_line.split()
            if len(parts) < 3:
                return None, None, None
            method, path, version = parts[0], parts[1], parts[2]
            if path == "/":
                path = "/index.html"
        except Exception:
            return None, None, None
        return method, path, version

    # ------------------------------------------------------------------
    # Header parsing
    # ------------------------------------------------------------------

    def prepare_headers(self, header_section):
        """Parse raw HTTP headers into a :class:`CaseInsensitiveDict`.

        :param header_section: String containing all header lines (no body).
        :returns: :class:`CaseInsensitiveDict` of ``{name: value}`` pairs.
        """
        headers = CaseInsensitiveDict()
        lines = header_section.split("\r\n")
        for line in lines[1:]:          # skip the request-line
            if ": " in line:
                key, val = line.split(": ", 1)
                headers[key.strip()] = val.strip()
        return headers

    def fetch_headers_body(self, request):
        """Split raw HTTP request into header section and body.

        :param request: Full raw HTTP request string.
        :returns: ``(header_section, body_section)`` tuple.
        """
        parts = request.split("\r\n\r\n", 1)
        _headers = parts[0]
        _body = parts[1] if len(parts) > 1 else ""
        return _headers, _body

    # ------------------------------------------------------------------
    # Cookie parsing  (RFC 6265)
    # ------------------------------------------------------------------

    def prepare_cookies(self, cookie_str):
        """Parse a ``Cookie`` header value into a :class:`CaseInsensitiveDict`.

        :param cookie_str: Raw cookie string, e.g.
            ``'session=abc123; lang=en'``.
        :returns: :class:`CaseInsensitiveDict` of cookie pairs.
        """
        cookie_dict = CaseInsensitiveDict()
        if isinstance(cookie_str, str):
            for pair in cookie_str.split(";"):
                pair = pair.strip()
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    cookie_dict[k.strip()] = v.strip()
        return cookie_dict

    # ------------------------------------------------------------------
    # Basic Auth parsing  (RFC 2617 / RFC 7235)
    # ------------------------------------------------------------------

    def prepare_auth(self, auth_header, url=""):
        """Decode a ``Basic`` ``Authorization`` header into ``(user, password)``.

        Sets ``self.auth`` if the header is valid Basic auth.

        :param auth_header: Value of the ``Authorization`` header.
        :param url: Request URL (unused; kept for API compatibility).
        """
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

    # ------------------------------------------------------------------
    # Body helpers
    # ------------------------------------------------------------------

    def prepare_body(self, data, files=None, json=None):
        """Store the request body and update ``Content-Length``.

        :param data: Body string or bytes.
        :param files: Unused (multipart placeholder).
        :param json: Unused (JSON helper placeholder).
        """
        self.body = data
        self.prepare_content_length(self.body)

    def prepare_content_length(self, body):
        """Set the ``Content-Length`` header from *body*.

        :param body: Body string or bytes.
        """
        if body:
            length = len(body.encode("utf-8") if isinstance(body, str) else body)
            self.headers["Content-Length"] = str(length)
        else:
            self.headers["Content-Length"] = "0"

    # ------------------------------------------------------------------
    # Main prepare entry point
    # ------------------------------------------------------------------

    def prepare(self, request, routes=None):
        """Parse the full HTTP request string.

        Populates :attr:`method`, :attr:`path`, :attr:`version`,
        :attr:`headers`, :attr:`body`, :attr:`cookies`, :attr:`auth`,
        and :attr:`hook`.

        :param request: Raw HTTP request string received from the socket.
        :param routes: Optional route mapping
            ``{(METHOD, path): handler_callable}``.
        """
        if not request:
            return

        preview = request[:120].replace("\r\n", " | ")
        print("[Request] prepare: {}".format(preview))

        # 1. Request line
        self.method, self.path, self.version = self.extract_request_line(request)
        print("[Request] {} {} {}".format(self.method, self.path, self.version))

        # 2. Headers + body split
        self._raw_headers, self._raw_body = self.fetch_headers_body(request)
        self.headers = self.prepare_headers(self._raw_headers)
        self.body = self._raw_body

        # 3. Cookie parsing (RFC 6265)
        cookie_str = self.headers.get("cookie", "")
        if cookie_str:
            self.cookies = self.prepare_cookies(cookie_str)

        # 4. Basic Auth parsing (RFC 2617)
        auth_header = self.headers.get("authorization", "")
        if auth_header:
            self.prepare_auth(auth_header)

        # 5. Route hook lookup
        if routes:
            self.routes = routes
            print("[Request] Routing {} {}".format(self.method, self.path))
            self.hook = routes.get((self.method, self.path))
            print("[Request] Hook found: {}".format(self.hook))
