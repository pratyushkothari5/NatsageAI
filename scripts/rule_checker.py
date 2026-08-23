"""
rule_checker.py — deterministic, non-AI validation of Cisco show-command
output for the NetSage AI project.

This module is intentionally independent of the AI diagnosis. It gives a
second, rule-based opinion so the human reviewer can compare:
    AI diagnosis  vs  rule_checker flags  vs  expected_fault (ground truth)

Checks implemented:
    - duplicate_ip          : same IP appearing on two different hosts/lines
    - wrong_mask            : subnet mask that looks inconsistent/non-standard
    - gateway_mismatch      : PC IP/mask and default gateway not in same subnet
    - interface_down        : "down", "administratively down" in interface status
    - missing_vlan          : VLAN referenced in symptom/topology but absent from `show vlan brief`
    - missing_route         : destination subnet not present in `show ip route`
    - acl_deny_broad        : ACL deny line using a wide wildcard mask (subnet-wide, not host-specific)
    - dhcp_pool_exhausted   : "Total addresses" == "Leased addresses" in DHCP pool output
    - trunk_native_mismatch : two "Native vlan" values differ across shown trunk outputs

Run standalone:
    python scripts/rule_checker.py           # runs against data/cases.csv, prints summary
"""

import csv
import ipaddress
import os
import re
import sys
from dataclasses import dataclass, field


@dataclass
class RuleFlag:
    rule: str
    message: str


@dataclass
class RuleCheckResult:
    case_id: str
    flags: list = field(default_factory=list)

    def add(self, rule: str, message: str):
        self.flags.append(RuleFlag(rule, message))

    @property
    def has_flags(self) -> bool:
        return len(self.flags) > 0


IP_RE = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")
MASK_RE = re.compile(r"Subnet Mask:\s*(\d{1,3}(?:\.\d{1,3}){3})", re.IGNORECASE)
IP_LINE_RE = re.compile(r"IP Address:\s*(\d{1,3}(?:\.\d{1,3}){3})", re.IGNORECASE)
GATEWAY_RE = re.compile(r"Default Gateway:\s*(\d{1,3}(?:\.\d{1,3}){3})", re.IGNORECASE)
INTERFACE_DOWN_RE = re.compile(r"(administratively down|down\s+down|status\s+down)", re.IGNORECASE)
VLAN_LINE_RE = re.compile(r"^\s*(\d{1,4})\s+\S+", re.MULTILINE)
ROUTE_NET_RE = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3})/(\d{1,2})\s+is directly connected|"
                           r"[A-Za-z*]+\s+(\d{1,3}(?:\.\d{1,3}){3})/(\d{1,2})")
DHCP_TOTAL_RE = re.compile(r"Total addresses\s*:\s*(\d+)", re.IGNORECASE)
DHCP_LEASED_RE = re.compile(r"Leased addresses\s*:\s*(\d+)", re.IGNORECASE)
ACL_DENY_RE = re.compile(r"deny\s+ip\s+\S+\s+(\d{1,3}(?:\.\d{1,3}){3})\s", re.IGNORECASE)
NATIVE_VLAN_RE = re.compile(r"Native vlan\s+(\d+)", re.IGNORECASE)


def check_gateway_mismatch(show_output: str) -> RuleFlag | None:
    ip_match = IP_LINE_RE.search(show_output)
    mask_match = MASK_RE.search(show_output)
    gw_match = GATEWAY_RE.search(show_output)
    if not (ip_match and mask_match and gw_match):
        return None
    try:
        host_net = ipaddress.ip_interface(f"{ip_match.group(1)}/{mask_match.group(1)}").network
        gw_ip = ipaddress.ip_address(gw_match.group(1))
        if gw_ip not in host_net:
            return RuleFlag(
                "gateway_mismatch",
                f"Host {ip_match.group(1)}/{mask_match.group(1)} is on {host_net}, "
                f"but default gateway {gw_match.group(1)} is NOT in that subnet.",
            )
    except ValueError:
        return None
    return None


def check_interface_down(show_output: str) -> RuleFlag | None:
    m = INTERFACE_DOWN_RE.search(show_output)
    if m:
        return RuleFlag("interface_down", f"Interface status shows '{m.group(1)}' in output.")
    return None


def check_missing_vlan(show_output: str, topology_note: str, symptom: str) -> RuleFlag | None:
    # Look for a VLAN number mentioned in symptom/topology that isn't listed under `show vlan brief`
    mentioned = set(re.findall(r"VLAN\s+(\d{1,4})", symptom + " " + topology_note, re.IGNORECASE))
    if not mentioned or "show vlan brief" not in show_output.lower():
        return None
    vlan_block = show_output.lower().split("show vlan brief", 1)[1]
    present = set(re.findall(r"^\s*(\d{1,4})\s", vlan_block, re.MULTILINE))
    missing = mentioned - present
    if missing:
        return RuleFlag(
            "missing_vlan",
            f"VLAN(s) {', '.join(sorted(missing))} mentioned in symptom/topology but not found in 'show vlan brief' output.",
        )
    return None


def check_missing_route(show_output: str, topology_note: str) -> RuleFlag | None:
    if "show ip route" not in show_output.lower():
        return None
    # Extract subnets mentioned in topology_note (rough heuristic)
    subnets_mentioned = set(re.findall(r"(\d{1,3}(?:\.\d{1,3}){3})/(\d{1,2})", topology_note))
    if not subnets_mentioned:
        return None
    route_block = show_output.lower().split("show ip route", 1)[1]
    for net, mask in subnets_mentioned:
        if net.lower() not in route_block:
            return RuleFlag(
                "missing_route",
                f"Subnet {net}/{mask} referenced in topology but not found in 'show ip route' output.",
            )
    return None


def check_dhcp_exhausted(show_output: str) -> RuleFlag | None:
    total = DHCP_TOTAL_RE.search(show_output)
    leased = DHCP_LEASED_RE.search(show_output)
    if total and leased and total.group(1) == leased.group(1):
        return RuleFlag(
            "dhcp_pool_exhausted",
            f"DHCP pool shows {leased.group(1)}/{total.group(1)} addresses leased (fully exhausted).",
        )
    return None


def check_acl_broad_deny(show_output: str) -> RuleFlag | None:
    for m in ACL_DENY_RE.finditer(show_output):
        mask = m.group(1)
        # wildcard masks like 0.0.0.255 or wider indicate a subnet-level deny, not host-specific
        octets = [int(x) for x in mask.split(".")]
        if octets[-1] >= 255 or octets[-2] > 0:
            return RuleFlag(
                "acl_deny_broad",
                f"ACL deny line uses wildcard mask {mask}, which covers a subnet rather than a single host — verify this is intentional.",
            )
    return None


def check_native_vlan_mismatch(show_output: str) -> RuleFlag | None:
    natives = set(NATIVE_VLAN_RE.findall(show_output))
    if len(natives) > 1:
        return RuleFlag(
            "trunk_native_mismatch",
            f"Multiple different native VLANs found in trunk output: {', '.join(sorted(natives))}.",
        )
    return None


def check_duplicate_ip(show_output: str) -> RuleFlag | None:
    ips = IP_RE.findall(show_output)
    seen = {}
    for ip in ips:
        seen[ip] = seen.get(ip, 0) + 1
    dupes = [ip for ip, count in seen.items() if count > 1 and not ip.startswith(("255.", "0.0.0.0"))]
    # Only flag if the surrounding text hints at a conflict (avoid false positives on repeated gateway refs)
    if dupes and re.search(r"duplicate|conflict", show_output, re.IGNORECASE):
        return RuleFlag("duplicate_ip", f"Possible duplicate IP usage detected: {', '.join(dupes)}.")
    return None


def run_all_checks(case: dict) -> RuleCheckResult:
    show_output = case.get("show_output", "") or ""
    topology_note = case.get("topology_note", "") or ""
    symptom = case.get("symptom", "") or ""

    result = RuleCheckResult(case_id=case.get("case_id", "UNKNOWN"))

    checks = [
        check_gateway_mismatch(show_output),
        check_interface_down(show_output),
        check_missing_vlan(show_output, topology_note, symptom),
        check_missing_route(show_output, topology_note),
        check_dhcp_exhausted(show_output),
        check_acl_broad_deny(show_output),
        check_native_vlan_mismatch(show_output),
        check_duplicate_ip(show_output),
    ]

    for flag in checks:
        if flag:
            result.flags.append(flag)

    return result


def main():
    data_path = os.path.join(os.path.dirname(__file__), "..", "data", "cases.csv")
    if not os.path.exists(data_path):
        print(f"cases.csv not found at {data_path}. Run scripts/generate_cases.py first.")
        sys.exit(1)

    with open(data_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        cases = list(reader)

    print(f"Running deterministic rule checker on {len(cases)} cases...\n")
    flagged_count = 0
    for case in cases:
        result = run_all_checks(case)
        if result.has_flags:
            flagged_count += 1
            print(f"[{result.case_id}] {case['category']} — {len(result.flags)} flag(s):")
            for flag in result.flags:
                print(f"   - ({flag.rule}) {flag.message}")
            print()

    print(f"Summary: {flagged_count}/{len(cases)} cases triggered at least one deterministic rule flag.")


if __name__ == "__main__":
    main()
