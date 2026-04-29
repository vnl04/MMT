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

    def route(self, path, methods=['GET']):
        def decorator(func):
            for method in methods:
                self.routes[(method.upper(), path)] = func

            func._route_path = path
            func._route_methods = methods

            def sync_wrapper(*args, **kwargs):
                print("[AsynapRous] running sync function... [{}] {}".format(methods, path))
                return func(*args, **kwargs)

            async def async_wrapper(*args, **kwargs):
                print("[AsynapRous] running Async function... [{}] {}".format(methods, path))
                return await func(*args, **kwargs)

            if inspect.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper

        return decorator

    def run(self):
        if not self.ip or not self.port:
            print("[AsynapRous] Need to call prepare_address(ip, port) first")
            return
        create_backend(self.ip, self.port, self.routes)
