#!/usr/bin/env python3
"""TRex benchmark: 64B multi-flow on both ports, 50 Mpps per port"""
import sys, time
sys.path.insert(0, "/opt/trex/scripts/automation/trex_control_plane/interactive")
from trex.stl.api import *

c = STLClient(server="127.0.0.1")
c.connect()
c.reset()

# Port 0: vary src IP for ECMP
vm0 = STLScVmRaw([
    STLVmFlowVar(name="src", min_value="10.0.1.1", max_value="10.0.1.254", size=4, op="inc"),
    STLVmWrFlowVar(fv_name="src", pkt_offset="IP.src"),
    STLVmFixIpv4(offset="IP")
])
pkt0 = STLPktBuilder(
    pkt=Ether()/IP(src="10.0.1.100",dst="10.10.1.1")/UDP(dport=12,sport=1025)/Raw(b"x"*16),
    vm=vm0
)

# Port 1: vary src IP
vm1 = STLScVmRaw([
    STLVmFlowVar(name="src", min_value="10.0.3.1", max_value="10.0.3.254", size=4, op="inc"),
    STLVmWrFlowVar(fv_name="src", pkt_offset="IP.src"),
    STLVmFixIpv4(offset="IP")
])
pkt1 = STLPktBuilder(
    pkt=Ether()/IP(src="10.0.3.100",dst="10.10.1.1")/UDP(dport=12,sport=1025)/Raw(b"x"*16),
    vm=vm1
)

c.add_streams(STLStream(packet=pkt0, mode=STLTXCont(pps=50000000)), ports=[0])
c.add_streams(STLStream(packet=pkt1, mode=STLTXCont(pps=50000000)), ports=[1])

print("Starting 50 Mpps per port (100 Mpps total) for 10 seconds...")
c.start(ports=[0,1], duration=10)

for i in range(5):
    time.sleep(2)
    stats = c.get_stats()
    g = stats["global"]
    print("  [%2ds] TX: %.2f Mpps (%.1f Gbps)" % (
        (i+1)*2, g.get("tx_pps",0)/1e6, g.get("tx_bps",0)/1e9))

c.wait_on_traffic()
stats = c.get_stats()

print("\n=== Final ===")
for port in [0, 1]:
    p = stats[port]
    print("  Port %d: TX %d pkts, RX %d pkts" % (port, p["opackets"], p["ipackets"]))

g = stats["global"]
print("  Total TX: %.2f Mpps (%.1f Gbps)" % (g.get("tx_pps",0)/1e6, g.get("tx_bps",0)/1e9))

c.disconnect()
print("Done!")
