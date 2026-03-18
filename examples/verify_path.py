#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# dependencies = ["pyzmq", "scapy"]
# ///
"""Quick verification that TX->DUT->RX path works with both TRex instances."""
import sys, os, time, argparse

def setup_trex_api():
    for path in ["/opt/trex/scripts/automation/trex_control_plane/interactive",
                 os.path.join(os.path.dirname(__file__), "..", "scripts",
                              "automation", "trex_control_plane", "interactive")]:
        path = os.path.normpath(path)
        if os.path.exists(os.path.join(path, "trex", "stl", "api.py")):
            ext_libs = os.path.normpath(os.path.join(path, "..", "..", "..", "external_libs"))
            if os.path.exists(ext_libs):
                os.environ["TREX_EXT_LIBS"] = ext_libs
            sys.path.insert(0, path)
            return True
    return False

def main():
    parser = argparse.ArgumentParser(description="Verify TX->DUT->RX path")
    parser.add_argument("--tx-server", required=True)
    parser.add_argument("--rx-server", required=True)
    args = parser.parse_args()

    if not setup_trex_api():
        print("ERROR: TRex API not found"); sys.exit(1)

    from trex.stl.api import (STLClient, STLStream, STLTXCont,
                               STLPktBuilder, Ether, IP, UDP, Raw)

    print("Connecting to TX TRex at %s..." % args.tx_server)
    tx = STLClient(server=args.tx_server)
    tx.connect()
    tx.reset()

    print("Connecting to RX TRex at %s..." % args.rx_server)
    rx = STLClient(server=args.rx_server)
    rx.connect()
    rx.reset()
    rx.clear_stats()

    # Send 1M packets at 100kpps (low rate, 10s)
    pkt = STLPktBuilder(
        pkt=Ether()/IP(src="10.0.1.100", dst="10.10.1.1")/
            UDP(dport=12, sport=1025)/Raw(b"x"*16))
    tx.add_streams(STLStream(packet=pkt, mode=STLTXCont(pps=100000)), ports=[0])

    print("Sending 100kpps on TX port 0 for 5 seconds...")
    tx.start(ports=[0], duration=5)
    tx.wait_on_traffic(ports=[0])
    time.sleep(1)

    tx_stats = tx.get_stats()
    rx_stats = rx.get_stats()

    tx_pkts = tx_stats[0]["opackets"]
    rx0 = rx_stats[0]["ipackets"]
    rx1 = rx_stats[1]["ipackets"]

    print("\n=== Path Verification ===")
    print("  TX sent:     %d packets" % tx_pkts)
    print("  RX port 0:   %d packets" % rx0)
    print("  RX port 1:   %d packets" % rx1)
    print("  RX total:    %d packets" % (rx0 + rx1))
    loss = tx_pkts - (rx0 + rx1)
    print("  Loss:        %d packets (%.3f%%)" % (loss, loss/tx_pkts*100 if tx_pkts else 0))

    if rx0 + rx1 > 0:
        print("\n  PATH OK - traffic flows TX -> DUT -> RX")
    else:
        print("\n  PATH BROKEN - no packets received on RX side!")
        print("  Check: VPP DUT running? Routes configured? MACs correct?")

    tx.disconnect()
    rx.disconnect()

if __name__ == "__main__":
    main()
