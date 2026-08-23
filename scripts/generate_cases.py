"""
generate_cases.py
Generates data/cases.csv — 32 troubleshooting cases across 8 network fault
categories for the NetSage AI project (Cisco AICTE VIP Program 2026).

Run:
    python scripts/generate_cases.py
"""

import csv
import os

CASES = [
    # ---------------- VLAN ----------------
    {
        "case_id": "C001",
        "category": "VLAN",
        "symptom": "PC in VLAN 30 gets an IP but cannot reach the file server also in VLAN 30.",
        "topology_note": "PC1 (Fa0/2) and Server1 (Fa0/3) both on SW1, meant to be VLAN 30. Trunk to core router carries VLANs 10,20,30.",
        "show_output": "SW1# show vlan brief\nVLAN Name                             Status    Ports\n10   Sales                            active    Fa0/4, Fa0/5\n20   HR                               active    Fa0/6\n30   Servers                          active    Fa0/3\n1    default                          active    Fa0/2, Fa0/7-24\n\nSW1# show interfaces fa0/2 switchport\nName: Fa0/2\nSwitchport: Enabled\nAdministrative Mode: static access\nAccess Mode VLAN: 1 (default)",
        "expected_fault": "Fa0/2 is assigned to VLAN 1 (default) instead of VLAN 30, so PC1 cannot reach Server1 which is in VLAN 30.",
        "osi_layer": "Layer 2",
        "concept_tag": "vlan_port_assignment",
        "severity": "Medium",
    },
    {
        "case_id": "C002",
        "category": "VLAN",
        "symptom": "Two switches connected by a trunk link, but hosts in VLAN 20 on SW2 cannot reach hosts in VLAN 20 on SW1.",
        "topology_note": "SW1 Gi0/1 <-> SW2 Gi0/1 trunk link. VLAN 20 exists on SW1 but was never created on SW2.",
        "show_output": "SW2# show vlan brief\nVLAN Name                             Status    Ports\n1    default                          active    Gi0/2-24\n10   Sales                            active    Fa0/5\n\nSW2# show interfaces trunk\nPort      Mode         Encapsulation  Status        Native vlan\nGi0/1     on           802.1q         trunking      1\n\nVlans allowed on trunk\nGi0/1     1-4094\n\nVlans in spanning tree forwarding state and not pruned\nGi0/1     1,10",
        "expected_fault": "VLAN 20 does not exist in SW2's VLAN database, so traffic tagged VLAN 20 arriving on the trunk is dropped.",
        "osi_layer": "Layer 2",
        "concept_tag": "missing_vlan",
        "severity": "High",
    },
    {
        "case_id": "C003",
        "category": "VLAN",
        "symptom": "PC cannot get an IP via DHCP after being moved to a new access port.",
        "topology_note": "PC moved from Fa0/2 (VLAN 10) to Fa0/8. Fa0/8 was previously configured as a trunk port for a test AP.",
        "show_output": "SW1# show interfaces fa0/8 switchport\nName: Fa0/8\nSwitchport: Enabled\nAdministrative Mode: trunk\nOperational Mode: trunk\nAccess Mode VLAN: 1 (default)",
        "expected_fault": "Fa0/8 is still configured as a trunk port instead of an access port in VLAN 10, so the PC's untagged DHCP request is not handled correctly.",
        "osi_layer": "Layer 2",
        "concept_tag": "port_mode_mismatch",
        "severity": "Medium",
    },
    {
        "case_id": "C004",
        "category": "VLAN",
        "symptom": "Voice VLAN phone works but the PC daisy-chained through the phone has no connectivity.",
        "topology_note": "Fa0/10 configured with voice VLAN 100 for IP phone; PC connects through phone's switch port.",
        "show_output": "SW1# show interfaces fa0/10 switchport\nName: Fa0/10\nSwitchport: Enabled\nAdministrative Mode: static access\nAccess Mode VLAN: 20 (Data)\nVoice VLAN: none",
        "expected_fault": "Voice VLAN is not configured on Fa0/10 (shows 'none'), so the phone and PC are both being forced into the same data VLAN, causing tagging conflicts.",
        "osi_layer": "Layer 2",
        "concept_tag": "voice_vlan_missing",
        "severity": "Low",
    },

    # ---------------- Default Gateway ----------------
    {
        "case_id": "C005",
        "category": "Gateway",
        "symptom": "PC gets an IP address but cannot reach any network outside its own subnet, including the gateway.",
        "topology_note": "PC1 in VLAN 10, subnet 192.168.10.0/24. Router sub-interface Gi0/0.10 configured for VLAN 10.",
        "show_output": "PC1> ipconfig\nIP Address: 192.168.10.25\nSubnet Mask: 255.255.255.0\nDefault Gateway: 192.168.20.1\n\nPC1> ping 192.168.20.1\nRequest timed out.",
        "expected_fault": "PC1's configured default gateway (192.168.20.1) is outside its own subnet (192.168.10.0/24); the gateway should be 192.168.10.1.",
        "osi_layer": "Layer 3",
        "concept_tag": "gateway_wrong_subnet",
        "severity": "High",
    },
    {
        "case_id": "C006",
        "category": "Gateway",
        "symptom": "PC can ping its own gateway but cannot reach a server on a different VLAN.",
        "topology_note": "Router-on-a-stick setup with sub-interfaces for VLAN 10 and VLAN 30.",
        "show_output": "R1# show ip interface brief\nInterface              IP-Address      Status     Protocol\nGigabitEthernet0/0.10  192.168.10.1    up         up\nGigabitEthernet0/0.30  unassigned      up         up",
        "expected_fault": "Sub-interface Gi0/0.30 has no IP address configured, so inter-VLAN routing for VLAN 30 cannot function.",
        "osi_layer": "Layer 3",
        "concept_tag": "subinterface_no_ip",
        "severity": "High",
    },
    {
        "case_id": "C007",
        "category": "Gateway",
        "symptom": "New PC on the network cannot ping the gateway even though cabling and VLAN are confirmed correct.",
        "topology_note": "PC statically configured. Subnet is 192.168.1.0/25 (mask 255.255.255.128).",
        "show_output": "PC1> ipconfig\nIP Address: 192.168.1.130\nSubnet Mask: 255.255.255.0\nDefault Gateway: 192.168.1.1",
        "expected_fault": "PC's subnet mask (255.255.255.0) is wrong for a /25 network; with the correct /25 mask, 192.168.1.130 falls in a different subnet than gateway 192.168.1.1.",
        "osi_layer": "Layer 3",
        "concept_tag": "wrong_subnet_mask",
        "severity": "Medium",
    },
    {
        "case_id": "C008",
        "category": "Gateway",
        "symptom": "All PCs in VLAN 40 lost connectivity to other VLANs after a router reload.",
        "topology_note": "Router-on-a-stick, sub-interface Gi0/0.40 for VLAN 40.",
        "show_output": "R1# show ip interface brief\nInterface              IP-Address      Status                  Protocol\nGigabitEthernet0/0.40  192.168.40.1    administratively down   down",
        "expected_fault": "Sub-interface Gi0/0.40 is administratively down (likely 'shutdown' was not removed after reload), so no traffic is routed for VLAN 40.",
        "osi_layer": "Layer 3",
        "concept_tag": "interface_admin_down",
        "severity": "High",
    },

    # ---------------- DHCP ----------------
    {
        "case_id": "C009",
        "category": "DHCP",
        "symptom": "PC shows an APIPA address (169.254.x.x) instead of getting an address from the DHCP server.",
        "topology_note": "PC in VLAN 10, DHCP server configured on router with pool for 192.168.10.0/24.",
        "show_output": "R1# show ip dhcp pool\nPool VLAN10 :\n Utilization mark (high/low)    : 100 / 0\n Subnet size (first/last)       : 0 / 0\n Total addresses                : 254\n Leased addresses               : 254\n Excluded addresses             : 0",
        "expected_fault": "DHCP pool for VLAN10 is fully exhausted (254/254 leased), so no new addresses can be issued and the PC falls back to APIPA.",
        "osi_layer": "Layer 3/7",
        "concept_tag": "dhcp_pool_exhausted",
        "severity": "High",
    },
    {
        "case_id": "C010",
        "category": "DHCP",
        "symptom": "PC in VLAN 20 (a different subnet from the router's LAN interface) is not receiving a DHCP address.",
        "topology_note": "DHCP server is centralized on R1's Gi0/0.10 interface. VLAN 20 uses sub-interface Gi0/0.20.",
        "show_output": "R1# show run interface gi0/0.20\ninterface GigabitEthernet0/0.20\n encapsulation dot1Q 20\n ip address 192.168.20.1 255.255.255.0\n(no ip helper-address configured)",
        "expected_fault": "Gi0/0.20 has no 'ip helper-address' pointing to the DHCP server, so DHCP broadcasts from VLAN 20 are never relayed.",
        "osi_layer": "Layer 3",
        "concept_tag": "missing_ip_helper",
        "severity": "High",
    },
    {
        "case_id": "C011",
        "category": "DHCP",
        "symptom": "PC receives an IP address but the gateway and DNS server fields are blank.",
        "topology_note": "DHCP pool configured for VLAN 30.",
        "show_output": "R1# show run | section dhcp pool VLAN30\nip dhcp pool VLAN30\n network 192.168.30.0 255.255.255.0\n(no default-router or dns-server statement present)",
        "expected_fault": "The DHCP pool is missing the 'default-router' and 'dns-server' statements, so clients get an IP but no gateway/DNS info.",
        "osi_layer": "Layer 7",
        "concept_tag": "dhcp_pool_incomplete",
        "severity": "Medium",
    },
    {
        "case_id": "C012",
        "category": "DHCP",
        "symptom": "Two PCs on the same VLAN intermittently lose connectivity and show duplicate IP warnings.",
        "topology_note": "One host statically configured with an address inside the DHCP pool's range.",
        "show_output": "PC3> ipconfig\nIP Address: 192.168.10.50 (static)\n\nR1# show ip dhcp pool VLAN10\n Excluded addresses : none configured\n Pool range          : 192.168.10.2 - 192.168.10.254",
        "expected_fault": "The static IP (192.168.10.50) falls inside the DHCP pool range and was never excluded, so DHCP later leased the same address to another host, causing a duplicate IP.",
        "osi_layer": "Layer 3",
        "concept_tag": "duplicate_ip_dhcp_overlap",
        "severity": "Medium",
    },

    # ---------------- DNS ----------------
    {
        "case_id": "C013",
        "category": "DNS",
        "symptom": "PC can ping the server by IP address but 'ping server.cisco.local' fails with 'Unknown host'.",
        "topology_note": "Internal DNS server at 192.168.10.5 hosts the cisco.local zone.",
        "show_output": "PC1> ipconfig /all\nDNS Servers: 0.0.0.0\n\nPC1> nslookup server.cisco.local\nDNS request timed out.",
        "expected_fault": "PC1 has no DNS server configured (0.0.0.0), so hostname resolution fails even though IP connectivity works.",
        "osi_layer": "Layer 7",
        "concept_tag": "dns_not_configured",
        "severity": "Medium",
    },
    {
        "case_id": "C014",
        "category": "DNS",
        "symptom": "All PCs in the building can browse the internal web server by name, except PCs in VLAN 40.",
        "topology_note": "DHCP pool for VLAN 40 recently recreated by a junior admin.",
        "show_output": "R1# show run | section dhcp pool VLAN40\nip dhcp pool VLAN40\n network 192.168.40.0 255.255.255.0\n default-router 192.168.40.1\n(no dns-server line)",
        "expected_fault": "VLAN 40's DHCP pool is missing the 'dns-server' statement, so clients receive an IP and gateway but no DNS server address.",
        "osi_layer": "Layer 7",
        "concept_tag": "dhcp_missing_dns_option",
        "severity": "Medium",
    },
    {
        "case_id": "C015",
        "category": "DNS",
        "symptom": "nslookup returns the wrong IP address for the internal file server after a recent server migration.",
        "topology_note": "Internal DNS server has an A record for fileserver.cisco.local.",
        "show_output": "DNS1# show run | include fileserver\n fileserver.cisco.local. IN A 192.168.10.20   ; old address, server migrated to 192.168.10.40",
        "expected_fault": "The DNS A record for fileserver.cisco.local still points to the old IP (192.168.10.20) and was not updated after the server's IP change to 192.168.10.40.",
        "osi_layer": "Layer 7",
        "concept_tag": "stale_dns_record",
        "severity": "Medium",
    },

    # ---------------- Routing ----------------
    {
        "case_id": "C016",
        "category": "Routing",
        "symptom": "PC gets an IP, gateway ping works, but cannot reach a server in VLAN 30. Gateway ping to remote router also fails.",
        "topology_note": "Two routers R1 and R2 connected via a serial link. VLAN 30 sits behind R2.",
        "show_output": "R1# show ip route\nGateway of last resort is not set\nC    192.168.10.0/24 is directly connected, GigabitEthernet0/0.10\nC    192.168.20.0/24 is directly connected, GigabitEthernet0/0.20\nC    10.0.0.0/30 is directly connected, Serial0/0/0\n(no route to 192.168.30.0/24)",
        "expected_fault": "R1 has no route to 192.168.30.0/24 (VLAN 30 behind R2); a static route or dynamic routing protocol needs to be configured.",
        "osi_layer": "Layer 3",
        "concept_tag": "missing_route",
        "severity": "High",
    },
    {
        "case_id": "C017",
        "category": "Routing",
        "symptom": "Branch office PCs can reach HQ server but HQ PCs cannot reach branch office server.",
        "topology_note": "OSPF running between R1 (HQ) and R2 (Branch).",
        "show_output": "R1# show ip ospf neighbor\n(empty - no neighbors listed)\n\nR1# show run | section router ospf\nrouter ospf 1\n network 192.168.10.0 0.0.0.255 area 0\n(serial interface network statement missing)",
        "expected_fault": "R1's OSPF process is missing the network statement for the serial link to R2, so no OSPF neighbor relationship forms and routes are not exchanged.",
        "osi_layer": "Layer 3",
        "concept_tag": "ospf_neighbor_down",
        "severity": "High",
    },
    {
        "case_id": "C018",
        "category": "Routing",
        "symptom": "Static route was configured for a remote subnet, but traffic to it is still failing.",
        "topology_note": "R1 has a static route toward 192.168.50.0/24 via next hop 10.0.0.6.",
        "show_output": "R1# show ip route static\nS    192.168.50.0/24 [1/0] via 10.0.0.6\n\nR1# ping 10.0.0.6\nRequest timed out.",
        "expected_fault": "The static route's next hop (10.0.0.6) is unreachable, likely a wrong next-hop IP or the far-end interface is down; the route itself is syntactically correct but non-functional.",
        "osi_layer": "Layer 3",
        "concept_tag": "unreachable_next_hop",
        "severity": "Medium",
    },
    {
        "case_id": "C019",
        "category": "Routing",
        "symptom": "Intermittent packet loss to a remote subnet reachable via two paths.",
        "topology_note": "Router has two static routes to 192.168.60.0/24 with different administrative distances suspected.",
        "show_output": "R1# show ip route 192.168.60.0\nRouting entry for 192.168.60.0/24\n  Known via \"static\", distance 1, metric 0\n  Routing Descriptor Blocks:\n  * 10.0.0.14 (down/unreachable)\n    10.0.0.10, via Serial0/0/1",
        "expected_fault": "The preferred static route via 10.0.0.14 is down but still installed in the table intermittently, causing traffic to blackhole instead of consistently using the working path via 10.0.0.10.",
        "osi_layer": "Layer 3",
        "concept_tag": "flapping_route",
        "severity": "Medium",
    },

    # ---------------- ACL ----------------
    {
        "case_id": "C020",
        "category": "ACL",
        "symptom": "PC in VLAN 10 can ping the server in VLAN 30 but web browsing (HTTP) to it fails.",
        "topology_note": "Extended ACL applied inbound on R1's Gi0/0.30 interface.",
        "show_output": "R1# show access-lists 101\nExtended IP access list 101\n 10 permit icmp any any\n 20 deny tcp any any eq 80\n 30 permit ip any any\n\nR1# show ip interface gi0/0.30 | include access list\n  Inbound  access list is 101",
        "expected_fault": "ACL 101 explicitly denies TCP port 80 (HTTP) before the final permit any, blocking web traffic while ICMP is still allowed.",
        "osi_layer": "Layer 3/4",
        "concept_tag": "acl_blocking_port",
        "severity": "Medium",
    },
    {
        "case_id": "C021",
        "category": "ACL",
        "symptom": "After applying a new security ACL, an entire subnet lost all connectivity, not just the intended host.",
        "topology_note": "ACL meant to block only host 192.168.10.50 from reaching the server subnet.",
        "show_output": "R1# show access-lists 105\nExtended IP access list 105\n 10 deny ip 192.168.10.0 0.0.0.255 any\n 20 permit ip any any",
        "expected_fault": "The ACL uses a wildcard mask covering the entire 192.168.10.0/24 subnet (0.0.0.255) instead of a host-specific wildcard (0.0.0.0) for 192.168.10.50, blocking the whole subnet.",
        "osi_layer": "Layer 3",
        "concept_tag": "acl_wildcard_too_broad",
        "severity": "High",
    },
    {
        "case_id": "C022",
        "category": "ACL",
        "symptom": "Remote management via SSH to a router works from one admin PC but not another on the same VLAN.",
        "topology_note": "ACL applied to VTY lines restricting SSH access to specific management hosts.",
        "show_output": "R1# show run | section line vty\nline vty 0 4\n access-class 10 in\n\nR1# show access-lists 10\nStandard IP access list 10\n 10 permit host 192.168.10.5",
        "expected_fault": "The VTY access-class ACL only permits host 192.168.10.5; the second admin PC's IP is not in the ACL, so its SSH attempts are implicitly denied.",
        "osi_layer": "Layer 7",
        "concept_tag": "acl_vty_restriction",
        "severity": "Low",
    },
    {
        "case_id": "C023",
        "category": "ACL",
        "symptom": "PC gets an IP, gateway ping works, cannot reach server in VLAN 30. Confidence should stay medium until route/ACL evidence is shown.",
        "topology_note": "Matches the example case from the problem statement: possible inter-VLAN routing or ACL issue at Layer 3/4.",
        "show_output": "R1# show ip route\nC    192.168.30.0/24 is directly connected, GigabitEthernet0/0.30\n\nR1# show access-lists\nExtended IP access list SERVER_ACL\n 10 deny ip 192.168.10.0 0.0.0.255 192.168.30.0 0.0.0.255\n 20 permit ip any any\n\nR1# show interfaces trunk\nPort      Mode   Encapsulation  Status     Native vlan\nGi0/1     on     802.1q         trunking   1",
        "expected_fault": "A route to VLAN 30 exists, but ACL SERVER_ACL explicitly denies traffic from 192.168.10.0/24 to 192.168.30.0/24, blocking the PC from reaching the server.",
        "osi_layer": "Layer 3/4",
        "concept_tag": "acl_interVLAN_block",
        "severity": "Medium",
    },

    # ---------------- NAT ----------------
    {
        "case_id": "C024",
        "category": "NAT",
        "symptom": "Internal PCs can ping each other and the router but cannot reach the simulated internet (ISP router).",
        "topology_note": "R1 configured with NAT overload on the outside interface.",
        "show_output": "R1# show ip nat translations\n(no translations present)\n\nR1# show run | include ip nat\n ip nat inside\n(no 'ip nat outside' found on any interface)",
        "expected_fault": "No interface is configured with 'ip nat outside', so NAT never triggers translation for outbound traffic even though 'ip nat inside' and the NAT statement exist.",
        "osi_layer": "Layer 3",
        "concept_tag": "nat_outside_missing",
        "severity": "High",
    },
    {
        "case_id": "C025",
        "category": "NAT",
        "symptom": "Only one internal PC at a time can access the internet; others fail until the first one stops.",
        "topology_note": "Static NAT (not overload/PAT) accidentally configured instead of dynamic NAT with overload.",
        "show_output": "R1# show run | include ip nat inside source\nip nat inside source static 192.168.10.10 203.0.113.5",
        "expected_fault": "A static one-to-one NAT translation is configured instead of 'ip nat inside source list <ACL> interface <outside-if> overload', so only the single mapped host can be translated at a time.",
        "osi_layer": "Layer 3",
        "concept_tag": "nat_static_instead_of_pat",
        "severity": "Medium",
    },
    {
        "case_id": "C026",
        "category": "NAT",
        "symptom": "PCs behind NAT can reach the internet, but an external partner cannot reach the internal web server via the public IP.",
        "topology_note": "Port forwarding (static NAT) intended for the internal web server on port 80.",
        "show_output": "R1# show run | include ip nat inside source static\nip nat inside source static tcp 192.168.10.20 8080 203.0.113.10 80",
        "expected_fault": "The static port forward maps the internal server's port 8080 to the public port 80, but the web server is actually listening on port 80 internally, so the port mapping is mismatched.",
        "osi_layer": "Layer 4",
        "concept_tag": "nat_port_mismatch",
        "severity": "Medium",
    },

    # ---------------- Wireless ----------------
    {
        "case_id": "C027",
        "category": "Wireless",
        "symptom": "Guest Wi-Fi users can reach the internal file server, which should be isolated from guest traffic.",
        "topology_note": "Guest SSID mapped to VLAN 50, internal server in VLAN 10. Security requirement: guest isolation.",
        "show_output": "R1# show access-lists\nExtended IP access list GUEST_ISOLATION\n 10 permit ip 192.168.50.0 0.0.0.255 any\n\nR1# show run interface gi0/0.50 | include access\n(no access-group applied)",
        "expected_fault": "A GUEST_ISOLATION ACL exists but permits all traffic and is not even applied to the guest VLAN interface, so guest devices have unrestricted access to internal VLANs.",
        "osi_layer": "Layer 3",
        "concept_tag": "guest_isolation_failure",
        "severity": "High",
    },
    {
        "case_id": "C028",
        "category": "Wireless",
        "symptom": "Laptop connects to the corporate Wi-Fi SSID but authentication repeatedly fails.",
        "topology_note": "WLAN configured with WPA2-Enterprise pointing to a RADIUS server.",
        "show_output": "WLC# show wlan 1\nSecurity: WPA2 Enterprise\nRADIUS Server: 192.168.10.100 (unreachable - last response: never)",
        "expected_fault": "The configured RADIUS server (192.168.10.100) is unreachable, so WPA2-Enterprise authentication requests never get a response and clients fail to authenticate.",
        "osi_layer": "Layer 7",
        "concept_tag": "radius_unreachable",
        "severity": "High",
    },
    {
        "case_id": "C029",
        "category": "Wireless",
        "symptom": "Wireless clients associate with the AP but never receive an IP address.",
        "topology_note": "AP's SSID mapped to VLAN 60, trunk port to switch carries VLANs 1,10,20,30.",
        "show_output": "SW1# show interfaces trunk\nVlans allowed on trunk\nGi0/2     1,10,20,30\n\nVlans in spanning tree forwarding state and not pruned\nGi0/2     1,10,20,30",
        "expected_fault": "VLAN 60 (the wireless client VLAN) is not included in the allowed VLAN list on the trunk to the AP, so DHCP/data traffic for wireless clients never reaches the rest of the network.",
        "osi_layer": "Layer 2",
        "concept_tag": "trunk_vlan_not_allowed",
        "severity": "High",
    },
    {
        "case_id": "C030",
        "category": "Wireless",
        "symptom": "Wireless signal is strong but throughput is very poor and connections frequently drop.",
        "topology_note": "Two APs installed close together for coverage overlap.",
        "show_output": "AP1# show controllers dot11Radio 0 | include Channel\nChannel: 6\n\nAP2# show controllers dot11Radio 0 | include Channel\nChannel: 6",
        "expected_fault": "Both nearby APs are configured on the same channel (6), causing co-channel interference and degraded throughput; channels should be staggered (e.g., 1, 6, 11).",
        "osi_layer": "Layer 1/2",
        "concept_tag": "wifi_channel_overlap",
        "severity": "Medium",
    },

    # ---------------- Extra mixed cases to comfortably exceed 30 ----------------
    {
        "case_id": "C031",
        "category": "Routing",
        "symptom": "Default route configured on edge router, but internal PCs still cannot reach the simulated internet server.",
        "topology_note": "R1 has 'ip route 0.0.0.0 0.0.0.0 <next-hop>' configured.",
        "show_output": "R1# show ip route\nGateway of last resort is 203.0.113.1 to network 0.0.0.0\nS*   0.0.0.0/0 [1/0] via 203.0.113.1\n\nR1# ping 203.0.113.1\nRequest timed out.",
        "expected_fault": "The default route's next hop (203.0.113.1) is itself unreachable — likely the ISP-facing interface is down or miscabled — so the default route is present but non-functional.",
        "osi_layer": "Layer 1/3",
        "concept_tag": "default_route_dead_next_hop",
        "severity": "High",
    },
    {
        "case_id": "C032",
        "category": "VLAN",
        "symptom": "After a switch replacement, all inter-VLAN traffic stopped even though VLANs and trunk look correctly configured.",
        "topology_note": "Replacement switch's trunk port native VLAN differs from the original switch.",
        "show_output": "SW1# show interfaces trunk\nPort      Mode   Encapsulation  Status     Native vlan\nGi0/1     on     802.1q         trunking   1\n\nSW2# show interfaces trunk\nPort      Mode   Encapsulation  Status     Native vlan\nGi0/1     on     802.1q         trunking   99",
        "expected_fault": "Native VLAN mismatch between SW1 (VLAN 1) and SW2 (VLAN 99) on the trunk link causes untagged traffic to be misassigned and generates VLAN mismatch errors.",
        "osi_layer": "Layer 2",
        "concept_tag": "native_vlan_mismatch",
        "severity": "Medium",
    },
]

FIELDNAMES = [
    "case_id", "category", "symptom", "topology_note", "show_output",
    "expected_fault", "osi_layer", "concept_tag", "severity",
]

def main():
    out_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "cases.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in CASES:
            writer.writerow(row)
    print(f"Wrote {len(CASES)} cases to {out_path}")

if __name__ == "__main__":
    main()
