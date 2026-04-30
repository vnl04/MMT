#
# Copyright (C) 2026 pdnguyen of HCMC University of Technology VNU-HCM.
# All rights reserved.
# This file is part of the CO3093/CO3094 course.
#
# AsynapRous release
#

"""
daemon.response
~~~~~~~~~~~~~~~~~

This module provides a Response object to construct HTTP responses
based on incoming requests. Supports MIME type detection, content loading
and header formatting.
"""
import datetime
import os
import mimetypes
from .dictionary import CaseInsensitiveDict

BASE_DIR = ""

class Response():
    """Constructs and serves HTTP responses for a custom web server."""

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
        "reason",
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

    def get_mime_type(self, path):
        """Guess MIME type from file extension."""
        try:
            mime_type, _ = mimetypes.guess_type(path)
        except Exception:
            return 'application/octet-stream'
        return mime_type or 'application/octet-stream'

    def prepare_content_type(self, mime_type='text/html'):
        """Set Content-Type header and return the base directory for the resource."""
        base_dir = ""

        if not hasattr(self, "headers") or self.headers is None:
            self.headers = {}

        main_type, sub_type = mime_type.split('/', 1)
        print("[Response] Processing main_type={} sub_type={}".format(main_type, sub_type))

        if main_type == 'text':
            self.headers['Content-Type'] = 'text/{}'.format(sub_type)
            if sub_type in ('plain', 'css', 'javascript'):
                base_dir = BASE_DIR + "static/"
            elif sub_type == 'html':
                base_dir = BASE_DIR + "www/"
            elif sub_type in ('csv', 'xml'):
                base_dir = BASE_DIR + "static/"
            else:
                base_dir = BASE_DIR + "static/"

        elif main_type == 'image':
            base_dir = BASE_DIR + "static/"
            self.headers['Content-Type'] = 'image/{}'.format(sub_type)

        elif main_type == 'application':
            if sub_type in ('json', 'octet-stream'):
                base_dir = BASE_DIR + "apps/"
            elif sub_type in ('xml', 'zip'):
                base_dir = BASE_DIR + "static/"
            else:
                base_dir = BASE_DIR + "apps/"
            self.headers['Content-Type'] = 'application/{}'.format(sub_type)

        elif main_type == 'video':
            base_dir = BASE_DIR + "static/"
            self.headers['Content-Type'] = 'video/{}'.format(sub_type)

        else:
            raise ValueError("Unsupported MIME type: {}/{}".format(main_type, sub_type))

        return base_dir

    def build_content(self, path, base_dir):
        """Read file from disk and return (length, bytes)."""
        filepath = os.path.join(base_dir, path.lstrip('/'))
        print("[Response] Serving the object at location {}".format(filepath))

        try:
            with open(filepath, "rb") as f:
                content = f.read()
        except Exception as e:
            print("[Response] build_content exception: {}".format(e))
            return -1, b""

        return len(content), content

    def build_response_header(self, request):
        """Build the full HTTP response header as bytes."""
        reqhdr = request.headers if request.headers else {}

        # Merge dynamic + static headers
        headers = {
            "Accept": "{}".format(reqhdr.get("Accept", "*/*")),
            "Accept-Language": "{}".format(reqhdr.get("Accept-Language", "en-US,en;q=0.9")),
            "Cache-Control": "no-cache",
            "Content-Type": "{}".format(self.headers.get('Content-Type', 'text/html')),
            "Content-Length": "{}".format(len(self._content)),
            "Date": "{}".format(datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")),
            "Connection": "close",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }

        # Build first status line
        status_line = "HTTP/1.1 {} {}\r\n".format(
            self.status_code or 200,
            self.reason or "OK"
        )

        # Format each header as "Key: Value\r\n"
        header_lines = ""
        for key, value in headers.items():
            header_lines += "{}: {}\r\n".format(key, value)

        fmt_header = status_line + header_lines + "\r\n"
        return fmt_header.encode('utf-8')

    def build_notfound(self):
        """Return a basic 404 Not Found response."""
        return (
            "HTTP/1.1 404 Not Found\r\n"
            "Accept-Ranges: bytes\r\n"
            "Content-Type: text/html\r\n"
            "Content-Length: 13\r\n"
            "Cache-Control: max-age=86000\r\n"
            "Connection: close\r\n"
            "\r\n"
            "404 Not Found"
        ).encode('utf-8')

    def build_json_response(self, content_bytes, extra_headers=None):
        """Build a 200 OK response wrapping JSON content.

        :param content_bytes: Response body as bytes.
        :param extra_headers: Optional dict of extra headers, e.g. {"Set-Cookie": "..."}.
        """
        self.status_code = 200
        self.reason = "OK"
        self.headers['Content-Type'] = 'application/json'
        self._content = content_bytes

        base_headers = (
            "Content-Type: application/json\r\n"
            "Content-Length: {}\r\n"
            "Cache-Control: no-cache\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS\r\n"
            "Access-Control-Allow-Headers: Content-Type, Authorization\r\n"
            "Connection: close\r\n"
        ).format(len(self._content))

        extra = ""
        if extra_headers:
            for k, v in extra_headers.items():
                extra += "{}: {}\r\n".format(k, v)

        full_header = "HTTP/1.1 200 OK\r\n" + base_headers + extra + "\r\n"
        return full_header.encode('utf-8') + self._content

    def build_cors_preflight(self):
        """Respond to OPTIONS preflight requests from browsers (CORS)."""
        return (
            "HTTP/1.1 204 No Content\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS\r\n"
            "Access-Control-Allow-Headers: Content-Type, Authorization\r\n"
            "Access-Control-Max-Age: 86400\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode('utf-8')

    def build_response(self, request, envelop_content=None):
        """Main method: build a complete HTTP response for the given request."""
        print("[Response] Start build response with req {}".format(request))

        path = request.path
        if not path:
            return self.build_notfound()

        mime_type = self.get_mime_type(path)
        print("[Response] {} path {} mime_type {}".format(request.method, path, mime_type))

        # Route to app hook — return JSON response
        if envelop_content is not None:
            return self.build_json_response(envelop_content)

        # Determine base_dir by mime type
        try:
            if path.endswith('.html') or mime_type == 'text/html':
                base_dir = self.prepare_content_type(mime_type='text/html')

            elif mime_type == 'text/css':
                base_dir = self.prepare_content_type(mime_type='text/css')

            elif mime_type and mime_type.startswith('image/'):
                base_dir = self.prepare_content_type(mime_type=mime_type)

            elif mime_type in ('application/json', 'application/octet-stream'):
                base_dir = self.prepare_content_type(mime_type='application/json')

            elif mime_type and mime_type.startswith('text/'):
                base_dir = self.prepare_content_type(mime_type=mime_type)

            else:
                return self.build_notfound()

        except ValueError as e:
            print("[Response] MIME error: {}".format(e))
            return self.build_notfound()

        # Load the file content
        content_len, content = self.build_content(path, base_dir)
        if content_len < 0:
            return self.build_notfound()

        self._content = content
        self.status_code = 200
        self.reason = "OK"

        # Build and return full response
        self._header = self.build_response_header(request)
        return self._header + self._content
