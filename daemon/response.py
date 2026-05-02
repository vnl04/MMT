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
daemon.response
~~~~~~~~~~~~~~~~~

Constructs HTTP responses for the custom web server.
Supports MIME type detection, static file serving, JSON API responses,
CORS preflight, and 404 / 401 error responses.

RFC references implemented:
  - RFC 7230  HTTP/1.1 Message Syntax
  - RFC 6265  HTTP State Management (Set-Cookie)
  - RFC 7235  HTTP/1.1 Authentication (WWW-Authenticate)
"""

import datetime
import os
import mimetypes
from .dictionary import CaseInsensitiveDict

# Project root (folder that contains daemon/, www/, apps/) — not cwd-relative.
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = _PKG_ROOT if _PKG_ROOT.endswith(os.sep) else _PKG_ROOT + os.sep


class Response:
    """Constructs and serves HTTP responses for a custom web server.

    Usage::

      >>> resp = Response()
      >>> raw = resp.build_response(request)
      >>> conn.sendall(raw)
    """

    __attrs__ = [
        "_content",
        "_header",
        "status_code",
        "method",
        "headers",
        "url",
        "history",
        "encoding",
        "reason",
        "cookies",
        "elapsed",
        "request",
        "body",
    ]

    def __init__(self, request=None):
        self._content = b""
        self._content_consumed = False
        self._next = None
        self._header = b""

        self.status_code = None
        self.headers = {}
        self.url = None
        self.encoding = None
        self.history = []
        self.reason = None
        self.cookies = CaseInsensitiveDict()
        self.elapsed = datetime.timedelta(0)
        self.request = request

    # ------------------------------------------------------------------
    # MIME helpers
    # ------------------------------------------------------------------

    def get_mime_type(self, path):
        """Guess MIME type from file extension.

        :param path: File path string.
        :returns: MIME type string, e.g. ``'text/html'``.
        """
        try:
            mime_type, _ = mimetypes.guess_type(path)
        except Exception:
            return "application/octet-stream"
        return mime_type or "application/octet-stream"

    def prepare_content_type(self, mime_type="text/html"):
        """Set the ``Content-Type`` response header and return the base
        directory from which the requested file should be read.

        :param mime_type: Full MIME type string, e.g. ``'text/css'``.
        :returns: Base directory path (str).
        :raises ValueError: For unsupported MIME main types.
        """
        base_dir = ""

        if not hasattr(self, "headers") or self.headers is None:
            self.headers = {}

        main_type, sub_type = mime_type.split("/", 1)
        print("[Response] Processing main_type={} sub_type={}".format(main_type, sub_type))

        if main_type == "text":
            self.headers["Content-Type"] = "text/{}".format(sub_type)
            if sub_type in ("plain", "css", "javascript", "csv", "xml"):
                base_dir = BASE_DIR + "static/"
            elif sub_type == "html":
                base_dir = BASE_DIR + "www/"
            else:
                base_dir = BASE_DIR + "static/"

        elif main_type == "image":
            base_dir = BASE_DIR + "static/"
            self.headers["Content-Type"] = "image/{}".format(sub_type)

        elif main_type == "application":
            if sub_type in ("json", "octet-stream"):
                base_dir = BASE_DIR + "apps/"
            elif sub_type in ("xml", "zip"):
                base_dir = BASE_DIR + "static/"
            else:
                base_dir = BASE_DIR + "apps/"
            self.headers["Content-Type"] = "application/{}".format(sub_type)

        elif main_type == "video":
            base_dir = BASE_DIR + "static/"
            self.headers["Content-Type"] = "video/{}".format(sub_type)

        elif main_type == "font":
            base_dir = BASE_DIR + "static/"
            self.headers["Content-Type"] = "font/{}".format(sub_type)

        else:
            raise ValueError("Unsupported MIME type: {}/{}".format(main_type, sub_type))

        return base_dir

    # ------------------------------------------------------------------
    # File loading
    # ------------------------------------------------------------------

    def build_content(self, path, base_dir):
        """Read a file from disk.

        :param path: URL path, e.g. ``'/index.html'``.
        :param base_dir: Base directory on disk.
        :returns: ``(content_length, content_bytes)`` or ``(-1, b'')``.
        """
        filepath = os.path.join(base_dir, path.lstrip("/"))
        print("[Response] Serving object at: {}".format(filepath))

        try:
            with open(filepath, "rb") as f:
                content = f.read()
        except Exception as e:
            print("[Response] build_content error: {}".format(e))
            return -1, b""

        return len(content), content

    # ------------------------------------------------------------------
    # Header building
    # ------------------------------------------------------------------

    def build_response_header(self, request):
        """Build the full HTTP status line + headers as bytes.

        Assembles standard headers including ``Content-Type``,
        ``Content-Length``, ``Date``, and CORS headers.

        :param request: Incoming :class:`Request` object.
        :returns: Encoded header bytes ending with ``\\r\\n\\r\\n``.
        """
        reqhdr = request.headers if request and request.headers else {}

        content_type = self.headers.get("Content-Type", "text/html")

        # Build ordered header dict
        hdr = {
            "Content-Type": content_type,
            "Content-Length": str(len(self._content)),
            "Date": datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT"),
            "Cache-Control": "no-cache",
            "Connection": "close",
            "Accept-Ranges": "bytes",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }

        # Mirror a few request headers back (informational only)
        accept = reqhdr.get("accept", "*/*") if hasattr(reqhdr, "get") else "*/*"
        hdr["Accept"] = accept

        status_line = "HTTP/1.1 {} {}\r\n".format(
            self.status_code or 200,
            self.reason or "OK",
        )

        # Format each header as "Key: Value\r\n"
        header_lines = ""
        for key, value in hdr.items():
            header_lines += "{}: {}\r\n".format(key, value)

        fmt_header = status_line + header_lines + "\r\n"
        return fmt_header.encode("utf-8")

    # ------------------------------------------------------------------
    # Specialised response builders
    # ------------------------------------------------------------------

    def build_notfound(self):
        """Return a ``404 Not Found`` response.

        :returns: Encoded bytes of the complete 404 HTTP response.
        """
        body = b"404 Not Found"
        return (
            "HTTP/1.1 404 Not Found\r\n"
            "Content-Type: text/html\r\n"
            "Content-Length: {}\r\n"
            "Cache-Control: no-cache\r\n"
            "Connection: close\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "\r\n"
        ).format(len(body)).encode("utf-8") + body

    def build_unauthorized(self, realm="AsynapRous"):
        """Return a ``401 Unauthorized`` response with ``WWW-Authenticate`` header.

        Implements RFC 7235 §4.1.

        :param realm: Authentication realm string.
        :returns: Encoded bytes of the complete 401 HTTP response.
        """
        body = b"401 Unauthorized"
        return (
            "HTTP/1.1 401 Unauthorized\r\n"
            'WWW-Authenticate: Basic realm="{}"\r\n'
            "Content-Type: text/plain\r\n"
            "Content-Length: {}\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).format(realm, len(body)).encode("utf-8") + body

    def build_cors_preflight(self):
        """Return a ``204 No Content`` response for CORS OPTIONS preflight.

        :returns: Encoded bytes of the CORS preflight response.
        """
        return (
            "HTTP/1.1 204 No Content\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS\r\n"
            "Access-Control-Allow-Headers: Content-Type, Authorization\r\n"
            "Access-Control-Max-Age: 86400\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("utf-8")

    def build_json_response(self, content_bytes, extra_headers=None):
        """Build a JSON HTTP response (default ``200 OK``).

        Supports ``Set-Cookie`` (RFC 6265) and other extra headers.

        Internal keys (stripped before sending; not forwarded to the client):
          * ``__status`` — HTTP status code as string, e.g. ``\"401\"``
          * ``__reason`` — reason phrase, e.g. ``\"Unauthorized\"``

        :param content_bytes: Response body as bytes.
        :param extra_headers: Optional header dict merged into the response.
        :returns: Complete encoded HTTP response bytes.
        """
        if not isinstance(content_bytes, bytes):
            content_bytes = str(content_bytes).encode("utf-8")

        status_code = 200
        reason_phrase = "OK"

        hdrs = {}
        if extra_headers:
            hdrs = dict(extra_headers)

        if "__status" in hdrs:
            status_code = int(hdrs.pop("__status"))
        if "__reason" in hdrs:
            reason_phrase = hdrs.pop("__reason")

        self.status_code = status_code
        self.reason = reason_phrase
        self._content = content_bytes

        base = (
            "HTTP/1.1 {code} {reason}\r\n"
            "Content-Type: application/json\r\n"
            "Content-Length: {clen}\r\n"
            "Date: {date}\r\n"
            "Cache-Control: no-cache\r\n"
            "Connection: close\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS\r\n"
            "Access-Control-Allow-Headers: Content-Type, Authorization\r\n"
        ).format(
            code=status_code,
            reason=reason_phrase,
            clen=len(self._content),
            date=datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT"),
        )

        extra = ""
        for k, v in hdrs.items():
            extra += "{}: {}\r\n".format(k, v)

        return (base + extra + "\r\n").encode("utf-8") + self._content

    # ------------------------------------------------------------------
    # Main response builder
    # ------------------------------------------------------------------

    def build_response(self, request, envelop_content=None):
        """Build a complete HTTP response for *request*.

        Detects MIME type from the requested path, reads the file from
        disk, assembles headers, and returns the complete response bytes.

        If *envelop_content* is provided it is used as the body directly
        (for app-hook JSON responses).

        :param request: Incoming :class:`Request` object.
        :param envelop_content: Optional bytes body (bypasses file lookup).
        :returns: Complete encoded HTTP response bytes.
        """
        print("[Response] build_response for request: {}".format(request))

        if envelop_content is not None:
            return self.build_json_response(envelop_content)

        path = request.path if request else None
        if not path:
            return self.build_notfound()

        mime_type = self.get_mime_type(path)
        print("[Response] {} {} mime_type={}".format(
            request.method, path, mime_type))

        # Resolve base_dir from MIME type
        try:
            if path.endswith(".html") or mime_type == "text/html":
                base_dir = self.prepare_content_type("text/html")
            elif mime_type == "text/css":
                base_dir = self.prepare_content_type("text/css")
            elif mime_type and mime_type.startswith("text/javascript"):
                base_dir = self.prepare_content_type("text/javascript")
            elif mime_type and mime_type.startswith("image/"):
                base_dir = self.prepare_content_type(mime_type)
            elif mime_type in ("application/json", "application/octet-stream"):
                base_dir = self.prepare_content_type("application/json")
            elif mime_type and mime_type.startswith("text/"):
                base_dir = self.prepare_content_type(mime_type)
            elif mime_type and mime_type.startswith("font/"):
                base_dir = self.prepare_content_type(mime_type)
            else:
                print("[Response] Unsupported MIME {} for path {}".format(mime_type, path))
                return self.build_notfound()
        except ValueError as e:
            print("[Response] MIME error: {}".format(e))
            return self.build_notfound()

        # Load file
        content_len, content = self.build_content(path, base_dir)
        if content_len < 0:
            return self.build_notfound()

        self._content = content
        self.status_code = 200
        self.reason = "OK"

        self._header = self.build_response_header(request)
        return self._header + self._content
