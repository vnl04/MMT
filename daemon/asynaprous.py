#
# Copyright (C) 2026 pdnguyen of HCMC University of Technology VNU-HCM.
# All rights reserved.
# This file is part of the CO3093/CO3094 course.
#
# AsynapRous release
#

"""
daemon.asynaprous
~~~~~~~~~~~~~~~~~

Lightweight web app router for RESTful URL endpoints.

FIX (Bug 3 / Bug 4): The ``route`` decorator previously returned a
*wrapper* function instead of the original *func*.  That broke
``inspect.iscoroutinefunction`` on handlers and made stacked ``@app.route``
decorators confusing. The fixed decorator registers the original *func* in
``self.routes`` and returns *func* unchanged.
"""

from .backend import create_backend
import asyncio
import inspect


class AsynapRous:
    """Decorator-based routing + TCP server launcher."""

    def __init__(self):
        self.routes = {}
        self.ip = None
        self.port = None

    def prepare_address(self, ip, port):
        self.ip = ip
        self.port = port

    def route(self, path, methods=None):
        """Register *func* as the handler for *path* and each method in *methods*.

        Returns the original *func* unmodified (see module docstring).

        :param path: URL path string, e.g. ``'/login'``.
        :param methods: List of HTTP method strings (default ``['GET']``).
        """
        if methods is None:
            methods = ['GET']

        def decorator(func):
            for method in methods:
                key = (method.upper(), path)
                self.routes[key] = func
                print("[AsynapRous] registered route {} {}".format(method.upper(), path))

            # Store lightweight metadata on the handler (optional, for logging)
            func._route_path = path
            func._route_methods = methods

            return func

        return decorator

    def run(self):
        if not self.ip or not self.port:
            print("[AsynapRous] Need to call prepare_address(ip, port) first")
            return
        create_backend(self.ip, self.port, self.routes)
