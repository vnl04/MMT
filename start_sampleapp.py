#
# Copyright (C) 2026 pdnguyen of HCMC University of Technology VNU-HCM.
# All rights reserved.
# This file is part of the CO3093/CO3094 course,
# and is released under the "MIT License Agreement". Please see the LICENSE
# file that should have been included as part of this package.
#
# AsynapRous release
#
# The authors hereby grant to Licensee personal permission to use
# and modify the Licensed Source Code for the sole purpose of studying
# while attending the course
#


"""
start_sampleapp
~~~~~~~~~~~~~~~~~

Entry point for the AsynapRous sample webapp.

Supports an optional integrated P2P listener port. When enabled, the app can
receive direct peer messages without a separate ``start_peer.py`` process.
"""

import argparse

from apps import create_sampleapp

PORT = 2026
P2P_PORT = 7000

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog='SampleApp',
        description='AsynapRous webapp with optional integrated P2P listener',
        epilog='Backend daemon for the AsynapRous chat application',
    )
    parser.add_argument('--server-ip', default='0.0.0.0')
    parser.add_argument('--server-port', type=int, default=PORT)
    parser.add_argument(
        '--p2p-port',
        type=int,
        default=P2P_PORT,
        help='Initial TCP port for direct peer messages (0 disables startup listener)',
    )

    args = parser.parse_args()
    ip = args.server_ip
    port = args.server_port

    create_sampleapp(ip, port, args.p2p_port)
