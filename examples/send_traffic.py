#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# dependencies = ["pyzmq", "scapy"]
# ///
"""
TRex simple traffic test - sends 1 Mpps UDP for 10 seconds.

Can run from ANY machine that can reach the TRex server:
  uv run send_traffic.py --server 10.0.0.1

Or inside the TRex container:
  docker exec trex python3 /opt/trex/examples/send_traffic.py

Prerequisites:
  - TRex server running (see main README)
  - uv installed: curl -LsSf https://astral.sh/uv/install.sh | sh
  - Network access to TRex host on ports 4500/4501
"""
import argparse
import sys
import os

def setup_trex_api():
    """Find and add TRex Python API to sys.path.

    Works both inside the Docker container and from the repo checkout.
    The bundled pyzmq-ctypes has a fallback to system pyzmq, so this
    works on any platform as long as pyzmq is pip/uv-installed.
    """
    search_paths = [
        "/opt/trex/scripts/automation/trex_control_plane/interactive",
        os.path.join(os.path.dirname(__file__), "..", "scripts",
                     "automation", "trex_control_plane", "interactive"),
    ]

    for path in search_paths:
        path = os.path.normpath(path)
        if os.path.exists(os.path.join(path, "trex", "stl", "api.py")):
            ext_libs = os.path.normpath(os.path.join(
                path, "..", "..", "..", "external_libs"))
            if os.path.exists(ext_libs):
                os.environ["TREX_EXT_LIBS"] = ext_libs
            sys.path.insert(0, path)
            return True

    return False

def main():
    parser = argparse.ArgumentParser(description="TRex simple traffic test")
    parser.add_argument("--server", default="127.0.0.1",
                        help="TRex server IP (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=0,
                        help="TX port (default: 0)")
    parser.add_argument("--rate", default="1mpps",
                        help="Traffic rate (default: 1mpps)")
    parser.add_argument("--duration", type=int, default=10,
                        help="Duration in seconds (default: 10)")
    parser.add_argument("--size", type=int, default=64,
                        help="Packet size in bytes (default: 64)")
    args = parser.parse_args()

    if not setup_trex_api():
        print("ERROR: Could not find TRex Python API.")
        print("Make sure you're running from the trex-arm64-spark repo,")
        print("or inside the TRex Docker container.")
        sys.exit(1)

    from trex.stl.api import (STLClient, STLStream, STLTXCont,
                               STLPktBuilder, Ether, IP, UDP, Raw)

    c = STLClient(server=args.server)
    print("Connecting to TRex server at %s..." % args.server)
    c.connect()
    c.reset()

    # Build packet with padding to target size
    # Ether(14) + IP(20) + UDP(8) = 42 bytes header, + 4 FCS on wire
    pad_len = max(0, args.size - 42 - 4)
    pkt = STLPktBuilder(
        pkt=Ether()/IP(src="10.0.1.100", dst="10.10.1.1")/
            UDP(dport=12, sport=1025)/Raw(b"x" * pad_len)
    )

    c.add_streams(STLStream(packet=pkt, mode=STLTXCont()), ports=[args.port])

    print("Starting %s on port %d for %d seconds (%dB packets)..." % (
        args.rate, args.port, args.duration, args.size))
    c.start(ports=[args.port], mult=args.rate, duration=args.duration)
    c.wait_on_traffic(ports=[args.port])

    stats = c.get_stats()
    p = stats[args.port]
    g = stats["global"]

    print("\n=== Results ===")
    print("  TX packets: %d" % p["opackets"])
    print("  TX bytes:   %d" % p["obytes"])
    print("  TX rate:    %.2f Mpps (%.1f Gbps)" % (
        g.get("tx_pps", 0) / 1e6, g.get("tx_bps", 0) / 1e9))

    c.disconnect()
    print("Done!")

if __name__ == "__main__":
    main()
