#!/usr/bin/env python3
"""
Lab 4: Live Network Devices via Netmiko SSH
Building AI Agents for Network Operations

DROP-IN REPLACEMENT for ../../examples/mock_network_devices.py

LAB MODE:  USE_LIVE = False  (uses the same mock data as before)
AFTER THE LAB:  Set USE_LIVE = True and update DEVICE_CONFIG

How to swap in this module:
    # In agentic_network_bot_ollama.py or agentic_network_bot.py, replace:
    from mock_network_devices import (...)
    # with:
    from live_network_devices import (...)

All exported function signatures are identical to mock_network_devices so
the agentic bots need zero other changes.
"""

import subprocess
from typing import Dict, List, Optional

# ============================================================================
# TOGGLE: Mock fallback vs live SSH
# ============================================================================

USE_LIVE = False  # Flip to True with real devices after the lab

DEVICE_CONFIG = {
    "spine1": {"device_type": "arista_eos", "host": "192.168.0.11", "username": "admin", "password": "admin", "port": 22},
    "spine2": {"device_type": "arista_eos", "host": "192.168.0.12", "username": "admin", "password": "admin", "port": 22},
    "leaf1":  {"device_type": "arista_eos", "host": "192.168.0.21", "username": "admin", "password": "admin", "port": 22},
    "leaf2":  {"device_type": "arista_eos", "host": "192.168.0.22", "username": "admin", "password": "admin", "port": 22},
}

# ============================================================================
# MOCK DATA — mirrors mock_network_devices.py exactly
# ============================================================================

_MOCK_DEVICES = {
    "spine1": {
        "hostname": "spine1", "ip": "192.168.0.11", "role": "spine",
        "model": "cEOS", "version": "4.28.0F", "serial": "SPX2134567890",
        "uptime_days": 5,
        "interfaces": {
            "Ethernet1": {"description": "to_leaf1",  "status": "up",   "speed": "10G"},
            "Ethernet2": {"description": "to_leaf2",  "status": "up",   "speed": "10G"},
            "Ethernet3": {"description": "to_spine2", "status": "up",   "speed": "40G"},
            "Management1": {"description": "oob_management", "status": "up", "speed": "1G"},
        },
        "bgp": {
            "local_as": 65001, "router_id": "10.0.0.11",
            "neighbors": [
                {"ip": "10.1.1.1", "remote_as": 65011, "state": "Established", "uptime": "3d2h",  "prefixes": 150},
                {"ip": "10.1.1.3", "remote_as": 65012, "state": "Established", "uptime": "3d2h",  "prefixes": 200},
            ],
        },
    },
    "spine2": {
        "hostname": "spine2", "ip": "192.168.0.12", "role": "spine",
        "model": "cEOS", "version": "4.28.0F", "serial": "SPX2134567891",
        "uptime_days": 7,
        "interfaces": {
            "Ethernet1": {"description": "to_leaf1",  "status": "up", "speed": "10G"},
            "Ethernet2": {"description": "to_leaf2",  "status": "up", "speed": "10G"},
            "Ethernet3": {"description": "to_spine1", "status": "up", "speed": "40G"},
            "Management1": {"description": "oob_management", "status": "up", "speed": "1G"},
        },
        "bgp": {
            "local_as": 65001, "router_id": "10.0.0.12",
            "neighbors": [
                {"ip": "10.1.2.1", "remote_as": 65011, "state": "Established", "uptime": "5d1h",  "prefixes": 150},
                {"ip": "10.1.2.3", "remote_as": 65012, "state": "Established", "uptime": "5d1h",  "prefixes": 200},
            ],
        },
    },
    "leaf1": {
        "hostname": "leaf1", "ip": "192.168.0.21", "role": "leaf",
        "model": "cEOS", "version": "4.27.3F", "serial": "LFX2134567890",
        "uptime_days": 3,
        "interfaces": {
            "Ethernet1": {"description": "to_spine1",    "status": "up",   "speed": "10G"},
            "Ethernet2": {"description": "to_spine2",    "status": "up",   "speed": "10G"},
            "Ethernet3": {"description": "server_rack_1","status": "up",   "speed": "1G"},
            "Management1": {"description": "oob_management", "status": "up", "speed": "1G"},
        },
        "bgp": {
            "local_as": 65011, "router_id": "10.0.1.21",
            "neighbors": [
                {"ip": "10.1.1.0", "remote_as": 65001, "state": "Established", "uptime": "3d1h", "prefixes": 50},
                {"ip": "10.1.2.0", "remote_as": 65001, "state": "Established", "uptime": "3d1h", "prefixes": 50},
            ],
        },
    },
    "leaf2": {
        "hostname": "leaf2", "ip": "192.168.0.22", "role": "leaf",
        "model": "cEOS", "version": "4.27.3F", "serial": "LFX2134567891",
        "uptime_days": 2,
        "interfaces": {
            "Ethernet1": {"description": "to_spine1",    "status": "up",   "speed": "10G"},
            "Ethernet2": {"description": "to_spine2",    "status": "up",   "speed": "10G"},
            "Ethernet3": {"description": "server_rack_2","status": "down", "speed": "1G"},
            "Management1": {"description": "oob_management", "status": "up", "speed": "1G"},
        },
        "bgp": {
            "local_as": 65012, "router_id": "10.0.1.22",
            "neighbors": [
                {"ip": "10.1.1.2", "remote_as": 65001, "state": "Established", "uptime": "2d3h", "prefixes": 50},
                {"ip": "10.1.2.2", "remote_as": 65001, "state": "Idle",        "uptime": "0h",   "prefixes": 0},
            ],
        },
    },
}


# ============================================================================
# SSH HELPER
# ============================================================================

def _ssh_command(device_name: str, command: str) -> str:
    """Run a command on a device via Netmiko and return raw output."""
    try:
        from netmiko import ConnectHandler
    except ImportError:
        raise RuntimeError("netmiko not installed — pip install -r requirements.txt")

    cfg = DEVICE_CONFIG.get(device_name.lower())
    if not cfg:
        raise ValueError(f"'{device_name}' not in DEVICE_CONFIG")

    with ConnectHandler(**cfg) as conn:
        return conn.send_command(command, read_timeout=30)


def _parse_version_output(raw: str) -> Dict:
    """Extract basic fields from 'show version' output."""
    result = {"model": "unknown", "version": "unknown", "serial": "unknown", "uptime": "unknown"}
    for line in raw.splitlines():
        ll = line.lower()
        if "software image version" in ll or "software version" in ll:
            result["version"] = line.split(":")[-1].strip()
        elif "serial number" in ll:
            result["serial"] = line.split(":")[-1].strip()
        elif "uptime" in ll:
            result["uptime"] = line.split(":", 1)[-1].strip()
        elif "arista" in ll or "cisco" in ll or "juniper" in ll:
            result["model"] = line.strip()
    return result


def _parse_int_brief(raw: str) -> List[Dict]:
    """Parse 'show ip interface brief' into a list of interface dicts."""
    interfaces = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0][0].isupper():
            interfaces.append({
                "name": parts[0],
                "ip_address": parts[1] if parts[1] != "unassigned" else None,
                "status": parts[2].lower(),
                "protocol": parts[3].lower() if len(parts) > 3 else parts[2].lower(),
            })
    return interfaces


def _parse_bgp_summary(raw: str) -> Dict:
    """Parse 'show bgp summary' and return structured neighbor data."""
    neighbors = []
    local_as = None
    router_id = None
    in_neighbor_table = False

    for line in raw.splitlines():
        ll = line.lower()
        if "local as" in ll or "local as number" in ll:
            for tok in line.split():
                if tok.isdigit():
                    local_as = int(tok)
        if "router identifier" in ll or "router id" in ll:
            import re
            m = re.search(r"(\d+\.\d+\.\d+\.\d+)", line)
            if m:
                router_id = m.group(1)

        # Detect header row then parse data rows
        if "neighbor" in ll and "as" in ll and ("state" in ll or "pfxrcd" in ll):
            in_neighbor_table = True
            continue
        if in_neighbor_table and line.strip():
            parts = line.split()
            if len(parts) >= 4:
                import re
                if re.match(r"\d+\.\d+\.\d+\.\d+", parts[0]):
                    state = next(
                        (p for p in parts if p in ("Estab", "Established", "Idle", "Active", "Connect")),
                        "Unknown",
                    )
                    if state == "Estab":
                        state = "Established"
                    prefixes = 0
                    for p in reversed(parts):
                        if p.isdigit():
                            prefixes = int(p)
                            break
                    neighbors.append({
                        "ip": parts[0],
                        "remote_as": int(parts[1]) if parts[1].isdigit() else 0,
                        "state": state,
                        "uptime": parts[-2] if len(parts) > 5 else "unknown",
                        "prefixes": prefixes,
                    })

    return {"local_as": local_as, "router_id": router_id, "neighbors": neighbors}


# ============================================================================
# PUBLIC API — same signatures as mock_network_devices.py
# ============================================================================

def get_device_status(device: str) -> Dict:
    """
    Get operational status of a network device.
    SSH equivalent: show version
    """
    if not USE_LIVE:
        data = _MOCK_DEVICES.get(device.lower())
        if not data:
            return {"error": f"Device '{device}' not found", "available_devices": list(_MOCK_DEVICES)}
        return {
            "device": data["hostname"], "ip": data["ip"], "status": "up",
            "model": data["model"], "version": data["version"],
            "serial": data["serial"], "uptime": f"{data['uptime_days']}d", "role": data["role"],
        }

    try:
        raw = _ssh_command(device, "show version")
        parsed = _parse_version_output(raw)
        cfg = DEVICE_CONFIG.get(device.lower(), {})
        return {
            "device": device, "ip": cfg.get("host", "unknown"), "status": "up",
            "model": parsed["model"], "version": parsed["version"],
            "serial": parsed["serial"], "uptime": parsed["uptime"],
            "role": "unknown",  # derive from naming convention if needed
        }
    except Exception as exc:
        return {"error": str(exc), "device": device}


def get_interface_status(device: str, interface: str = None) -> Dict:
    """
    Get interface status for a device.
    SSH equivalent: show ip interface brief
    """
    if not USE_LIVE:
        data = _MOCK_DEVICES.get(device.lower())
        if not data:
            return {"error": f"Device '{device}' not found"}
        interfaces = data["interfaces"]
        if interface:
            if interface in interfaces:
                return {"device": device, "interface": interface, **interfaces[interface]}
            return {"error": f"Interface '{interface}' not on {device}", "available_interfaces": list(interfaces)}
        return {"device": device, "interfaces": [{"name": n, **d} for n, d in interfaces.items()]}

    try:
        raw = _ssh_command(device, "show ip interface brief")
        parsed = _parse_int_brief(raw)
        if interface:
            match = next((i for i in parsed if i["name"] == interface), None)
            if match:
                return {"device": device, "interface": interface,
                        "status": match["status"], "description": "live", "speed": "unknown"}
            return {"error": f"Interface '{interface}' not found", "available_interfaces": [i["name"] for i in parsed]}
        return {"device": device, "interfaces": parsed}
    except Exception as exc:
        return {"error": str(exc), "device": device}


def get_bgp_summary(device: str) -> Dict:
    """
    Get BGP neighbor summary from device.
    SSH equivalent: show bgp summary
    """
    if not USE_LIVE:
        data = _MOCK_DEVICES.get(device.lower())
        if not data:
            return {"error": f"Device '{device}' not found"}
        bgp = data["bgp"]
        established = sum(1 for n in bgp["neighbors"] if n["state"] == "Established")
        return {
            "device": device, "local_as": bgp["local_as"], "router_id": bgp["router_id"],
            "total_peers": len(bgp["neighbors"]), "established_peers": established,
            "neighbors": bgp["neighbors"],
        }

    try:
        raw = _ssh_command(device, "show bgp summary")
        parsed = _parse_bgp_summary(raw)
        established = sum(1 for n in parsed["neighbors"] if n["state"] == "Established")
        return {
            "device": device,
            "local_as": parsed["local_as"],
            "router_id": parsed["router_id"],
            "total_peers": len(parsed["neighbors"]),
            "established_peers": established,
            "neighbors": parsed["neighbors"],
        }
    except Exception as exc:
        return {"error": str(exc), "device": device}


def ping_device(target: str, count: int = 4) -> Dict:
    """
    Ping a target device/IP to check reachability.
    SSH equivalent: ping <target> repeat <count>

    Args:
        target: Device hostname or IP address
        count:  Number of ping packets (default 4)
    """
    if not USE_LIVE:
        target_data = _MOCK_DEVICES.get(target.lower())
        target_ip = target_data["ip"] if target_data else target
        reachable = target_data is not None
        return {
            "target": target,
            "ip": target_ip,
            "packets_sent": count,
            "packets_received": count if reachable else 0,
            "packet_loss": 0 if reachable else 100,
            "rtt_min": 0.5, "rtt_avg": 1.2, "rtt_max": 2.1,
            "status": "reachable" if reachable else "unreachable",
        }

    try:
        target_ip = target
        if target.lower() in DEVICE_CONFIG:
            target_ip = DEVICE_CONFIG[target.lower()]["host"]

        import subprocess
        result = subprocess.run(
            ["ping", "-c", str(count), target_ip],
            capture_output=True, text=True, timeout=15
        )
        success = result.returncode == 0
        return {
            "target": target,
            "ip": target_ip,
            "packets_sent": count,
            "packets_received": count if success else 0,
            "packet_loss": 0 if success else 100,
            "status": "reachable" if success else "unreachable",
            "raw_output": result.stdout[:300],
        }
    except Exception as exc:
        return {"error": str(exc), "target": target}


def execute_command(device: str, command: str) -> str:
    """
    Execute a show command on a device.
    SSH equivalent: ssh <device> '<command>'
    """
    if not command.strip().lower().startswith("show"):
        return "Error: Only 'show' commands are permitted for safety"

    if not USE_LIVE:
        data = _MOCK_DEVICES.get(device.lower())
        if not data:
            return f"Error: Device '{device}' not found"
        cmd = command.lower()
        if "show version" in cmd:
            return (f"Arista {data['model']}\nSerial: {data['serial']}\n"
                    f"Version: {data['version']}\nUptime: {data['uptime_days']} days")
        if "show ip interface brief" in cmd:
            lines = ["Interface         IP Address      Status    Protocol"]
            for name, d in data["interfaces"].items():
                ip = data["ip"] if "Management" in name else "unassigned"
                lines.append(f"{name:<17} {ip:<15} {d['status']:<9} {d['status']}")
            return "\n".join(lines)
        if "show bgp" in cmd or "show ip bgp" in cmd:
            bgp = data["bgp"]
            lines = [f"Router ID {bgp['router_id']}, AS {bgp['local_as']}",
                     "Neighbor        AS      State       Uptime    Prefixes"]
            for n in bgp["neighbors"]:
                lines.append(f"{n['ip']:<15} {n['remote_as']:<7} {n['state']:<11} {n['uptime']:<9} {n['prefixes']}")
            return "\n".join(lines)
        return f"Mock: command '{command}' not implemented. Try: show version, show ip interface brief, show bgp summary"

    try:
        return _ssh_command(device, command)
    except Exception as exc:
        return f"SSH error on {device}: {exc}"


def get_topology_info() -> Dict:
    """Return topology metadata (static — same in live and mock modes)."""
    return {
        "name": "Spine-Leaf Topology",
        "type": "2-spine, 2-leaf",
        "devices": {"spines": ["spine1", "spine2"], "leaves": ["leaf1", "leaf2"]},
        "links": [
            {"from": "spine1", "to": "leaf1", "interface": "Ethernet1"},
            {"from": "spine1", "to": "leaf2", "interface": "Ethernet2"},
            {"from": "spine2", "to": "leaf1", "interface": "Ethernet1"},
            {"from": "spine2", "to": "leaf2", "interface": "Ethernet2"},
            {"from": "spine1", "to": "spine2", "interface": "Ethernet3"},
        ],
        "management_network": "192.168.0.0/24",
        "underlay_protocol": "BGP",
        "overlay_protocol": "EVPN",
        "mode": "live SSH" if USE_LIVE else "mock",
    }


# ============================================================================
# SMOKE TEST
# ============================================================================

if __name__ == "__main__":
    import json

    mode = "LIVE SSH" if USE_LIVE else "MOCK DATA"
    print(f"🔧 live_network_devices.py  [{mode}]")
    print("=" * 70)
    print("Drop-in replacement for mock_network_devices.py")
    print(f"Set USE_LIVE = True to SSH into real devices.\n")

    print("get_device_status('spine1'):")
    print(json.dumps(get_device_status("spine1"), indent=2))

    print("\nget_bgp_summary('leaf2'):")
    print(json.dumps(get_bgp_summary("leaf2"), indent=2))

    print("\nget_interface_status('leaf2', 'Ethernet3'):")
    print(json.dumps(get_interface_status("leaf2", "Ethernet3"), indent=2))

    print("\nping_device('spine1', 'leaf1'):")
    print(json.dumps(ping_device("spine1", "leaf1"), indent=2))

    print("\nexecute_command('leaf2', 'show bgp summary'):")
    print(execute_command("leaf2", "show bgp summary"))

    print("\nget_topology_info():")
    print(json.dumps(get_topology_info(), indent=2))
