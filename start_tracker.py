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
start_tracker
~~~~~~~~~~~~~~~~~

Entry point for the chat tracker server.

The tracker is a simple centralised directory that peers register with
and query to discover each other.  Once two peers know each other's
IP/port they communicate directly (P2P) without going through the tracker.

Usage:
    python start_tracker.py
    python start_tracker.py --server-ip 0.0.0.0 --server-port 6000
"""

import argparse
from chat import run_tracker

TRACKER_PORT = 6000

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog='Tracker',
        description='Start the P2P chat tracker server',
        epilog='Tracker daemon for hybrid chat application'
    )
    parser.add_argument('--server-ip', default='0.0.0.0',
                        help='IP address to bind (default: 0.0.0.0)')
    parser.add_argument('--server-port', type=int, default=TRACKER_PORT,
                        help='Port number to bind (default: {})'.format(TRACKER_PORT))

    args = parser.parse_args()
    run_tracker(args.server_ip, args.server_port)
