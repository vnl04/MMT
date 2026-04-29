#
# Copyright (C) 2026 pdnguyen of HCMC University of Technology VNU-HCM.
# All rights reserved.
# This file is part of the CO3093/CO3094 course.
#
# AsynapRous release
#

from collections.abc import MutableMapping

class CaseInsensitiveDict(MutableMapping):
    """A dict subclass that does case-insensitive key lookups.

    Usage::

      >>> word = CaseInsensitiveDict(status_code='404', msg="Not found")
      >>> word['STATUS_CODE']
      '404'
    """

    def __init__(self, *args, **kwargs):
        self.store = {}
        self.update(dict(*args, **kwargs))

    def __getitem__(self, key):
        return self.store[key.lower()]

    def __setitem__(self, key, value):
        self.store[key.lower()] = value

    def __delitem__(self, key):
        del self.store[key.lower()]

    def __iter__(self):
        return iter(self.store)

    def __len__(self):
        return len(self.store)

    def __repr__(self):
        return str(dict(self.store))
