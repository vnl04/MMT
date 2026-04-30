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
start_peer
~~~~~~~~~~~~~~~~~

Entry point for launching a chat peer node.

Each peer registers with the tracker, then listens for direct incoming
connections from other peers and provides an interactive prompt for sending
messages.

Usage:
    python start_peer.py --username alice --peer-port 7001
    python start_peer.py --username bob   --peer-port 7002 \
                         --tracker-ip 192.168.56.114 --tracker-port 6000
"""

import argparse
import socket
from chat import ChatPeer

TRACKER_IP   = '127.0.0.1'
TRACKER_PORT = 6000
PEER_PORT    = 7000


def _get_local_ip():
    """Best-effort attempt to get the machine's outbound IP."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog='Peer',
        description='Start a chat peer node',
        epilog='Peer daemon for hybrid P2P chat application'
    )
    parser.add_argument('--username', required=True,
                        help='Display name for this peer')
    parser.add_argument('--peer-ip', default=None,
                        help='IP to advertise to other peers (default: auto-detect)')
    parser.add_argument('--peer-port', type=int, default=PEER_PORT,
                        help='Port this peer listens on for P2P messages (default: {})'.format(PEER_PORT))
    parser.add_argument('--tracker-ip', default=TRACKER_IP,
                        help='Tracker server IP (default: {})'.format(TRACKER_IP))
    parser.add_argument('--tracker-port', type=int, default=TRACKER_PORT,
                        help='Tracker server port (default: {})'.format(TRACKER_PORT))

    args = parser.parse_args()

    peer_ip = args.peer_ip if args.peer_ip else _get_local_ip()

    peer = ChatPeer(
        username=args.username,
        peer_ip=peer_ip,
        peer_port=args.peer_port,
        tracker_ip=args.tracker_ip,
        tracker_port=args.tracker_port,
    )

    if peer.start():
        peer.run_interactive()
    else:
        print("[Peer] Could not start. Is the tracker running?")
