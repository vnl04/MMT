#
# Copyright (C) 2026 pdnguyen of HCMC University of Technology VNU-HCM.
# All rights reserved.
# This file is part of the CO3093/CO3094 course.
#
# AsynapRous release
#

from urllib.parse import urlparse, unquote

def get_auth_from_url(url):
    """Extract (username, password) from a URL that contains auth info."""
    parsed = urlparse(url)
    try:
        auth = (unquote(parsed.username or ""), unquote(parsed.password or ""))
    except (AttributeError, TypeError):
        auth = ("", "")
    return auth
