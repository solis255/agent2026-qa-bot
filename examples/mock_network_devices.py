#!/usr/bin/env python3
"""
Mock Network Device Simulator
Building AI Agents for Network Operations - macOS Compatible

This module simulates Arista cEOS devices without requiring Containerlab.
All device responses are realistic but mocked for cross-platform compatibility.

Simulated Topology:
    spine1 (192.168.0.11) ─┬─ leaf1 (192.168.0.21)
                           └─ leaf2 (192.168.0.22)
    spine2 (192.168.0.12) ─┘
"""

import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import random


class MockNetworkDevice:
    """
    Simulates an Arista cEOS network device.
    
    Returns realistic output for common show commands without
    requiring actual network devices or Linux.
    """
    
    # Device inventory
    DEVICES = {
        "spine1": {
            "hostname": "spine1",
            "ip": "192.168.0.11",
            "role": "spine",
            "model": "cEOS",
            "version": "4.28.0F",
            "serial": "SPX2134567890",
            "uptime_days": 5,
            "interfaces": {
                "Ethernet1": {"description": "to_leaf1", "status": "up", "speed": "10G"},
                "Ethernet2": {"description": "to_leaf2", "status": "up", "speed": "10G"},
                "Ethernet3": {"description": "to_spine2", "status": "up", "speed": "40G"},
                "Management1": {"description": "oob_management", "status": "up", "speed": "1G"}
            },
            "bgp": {
                "local_as": 65001,
                "router_id": "10.0.0.11",
                "neighbors": [
                    {"ip": "10.1.1.1", "remote_as": 65011, "state": "Established", "uptime": "3d2h", "prefixes": 150},
                    {"ip": "10.1.1.3", "remote_as": 65012, "state": "Established", "uptime": "3d2h", "prefixes": 200}
                ]
            }
        },
        "spine2": {
            "hostname": "spine2",
            "ip": "192.168.0.12",
            "role": "spine",
            "model": "cEOS",
            "version": "4.28.0F",
            "serial": "SPX2134567891",
            "uptime_days": 7,
            "interfaces": {
                "Ethernet1": {"description": "to_leaf1", "status": "up", "speed": "10G"},
                "Ethernet2": {"description": "to_leaf2", "status": "up", "speed": "10G"},
                "Ethernet3": {"description": "to_spine1", "status": "up", "speed": "40G"},
                "Management1": {"description": "oob_management", "status": "up", "speed": "1G"}
            },
            "bgp": {
                "local_as": 65001,
                "router_id": "10.0.0.12",
                "neighbors": [
                    {"ip": "10.1.2.1", "remote_as": 65011, "state": "Established", "uptime": "5d1h", "prefixes": 150},
                    {"ip": "10.1.2.3", "remote_as": 65012, "state": "Established", "uptime": "5d1h", "prefixes": 200}
                ]
            }
        },
        "leaf1": {
            "hostname": "leaf1",
            "ip": "192.168.0.21",
            "role": "leaf",
            "model": "cEOS",
            "version": "4.27.3F",
            "serial": "LFX2134567890",
            "uptime_days": 3,
            "interfaces": {
                "Ethernet1": {"description": "to_spine1", "status": "up", "speed": "10G"},
                "Ethernet2": {"description": "to_spine2", "status": "up", "speed": "10G"},
                "Ethernet3": {"description": "server_rack_1", "status": "up", "speed": "1G"},
                "Management1": {"description": "oob_management", "status": "up", "speed": "1G"}
            },
            "bgp": {
                "local_as": 65011,
                "router_id": "10.0.1.21",
                "neighbors": [
                    {"ip": "10.1.1.0", "remote_as": 65001, "state": "Established", "uptime": "3d1h", "prefixes": 50},
                    {"ip": "10.1.2.0", "remote_as": 65001, "state": "Established", "uptime": "3d1h", "prefixes": 50}
                ]
            }
        },
        "leaf2": {
            "hostname": "leaf2",
            "ip": "192.168.0.22",
            "role": "leaf",
            "model": "cEOS",
            "version": "4.27.3F",
            "serial": "LFX2134567891",
            "uptime_days": 2,
            "interfaces": {
                "Ethernet1": {"description": "to_spine1", "status": "up", "speed": "10G"},
                "Ethernet2": {"description": "to_spine2", "status": "up", "speed": "10G"},
                "Ethernet3": {"description": "server_rack_2", "status": "down", "speed": "1G"},
                "Management1": {"description": "oob_management", "status": "up", "speed": "1G"}
            },
            "bgp": {
                "local_as": 65012,
                "router_id": "10.0.1.22",
                "neighbors": [
                    {"ip": "10.1.1.2", "remote_as": 65001, "state": "Established", "uptime": "2d3h", "prefixes": 50},
                    {"ip": "10.1.2.2", "remote_as": 65001, "state": "Idle", "uptime": "0h", "prefixes": 0}
                ]
            }
        }
    }
    
    @classmethod
    def get_device_data(cls, device_name: str) -> Optional[Dict]:
        """Get device configuration data."""
        return cls.DEVICES.get(device_name.lower())
    
    @classmethod
    def device_exists(cls, device_name: str) -> bool:
        """Check if device exists in topology."""
        return device_name.lower() in cls.DEVICES
    
    @classmethod
    def list_devices(cls) -> List[str]:
        """List all available devices."""
        return list(cls.DEVICES.keys())


def get_device_status(device: str) -> Dict:
    """
    Get operational status of a network device.
    
    Simulates: ssh {device} "show version"
    
    Args:
        device: Device hostname (spine1, spine2, leaf1, leaf2)
    
    Returns:
        Dict with device status information
    """
    device_data = MockNetworkDevice.get_device_data(device)
    
    if not device_data:
        return {
            "error": f"Device '{device}' not found",
            "available_devices": MockNetworkDevice.list_devices()
        }
    
    return {
        "device": device_data["hostname"],
        "ip": device_data["ip"],
        "status": "up",
        "model": device_data["model"],
        "version": device_data["version"],
        "serial": device_data["serial"],
        "uptime": f"{device_data['uptime_days']}d",
        "role": device_data["role"]
    }


def get_interface_status(device: str, interface: str = None) -> Dict:
    """
    Get interface status for a device.
    
    Simulates: ssh {device} "show interfaces status"
    
    Args:
        device: Device hostname
        interface: Specific interface name (optional)
    
    Returns:
        Dict with interface status
    """
    device_data = MockNetworkDevice.get_device_data(device)
    
    if not device_data:
        return {"error": f"Device '{device}' not found"}
    
    interfaces = device_data["interfaces"]
    
    # Return specific interface or all
    if interface:
        if interface in interfaces:
            return {
                "device": device,
                "interface": interface,
                **interfaces[interface]
            }
        else:
            return {
                "error": f"Interface '{interface}' not found on {device}",
                "available_interfaces": list(interfaces.keys())
            }
    
    # Return all interfaces
    return {
        "device": device,
        "interfaces": [
            {"name": name, **data}
            for name, data in interfaces.items()
        ]
    }


def get_bgp_summary(device: str) -> Dict:
    """
    Get BGP neighbor summary from device.
    
    Simulates: ssh {device} "show ip bgp summary"
    
    Args:
        device: Device hostname
    
    Returns:
        Dict with BGP summary information
    """
    device_data = MockNetworkDevice.get_device_data(device)
    
    if not device_data:
        return {"error": f"Device '{device}' not found"}
    
    bgp_data = device_data["bgp"]
    
    total_peers = len(bgp_data["neighbors"])
    established = sum(1 for n in bgp_data["neighbors"] if n["state"] == "Established")
    
    return {
        "device": device,
        "local_as": bgp_data["local_as"],
        "router_id": bgp_data["router_id"],
        "total_peers": total_peers,
        "established_peers": established,
        "neighbors": bgp_data["neighbors"]
    }


def ping_device(target: str, count: int = 4) -> Dict:
    """
    Simulate ping to a device.
    
    Args:
        target: Device hostname or IP
        count: Number of ping packets
    
    Returns:
        Dict with ping results
    """
    # Check if target is a known device
    device_data = MockNetworkDevice.get_device_data(target)
    
    if device_data:
        # Device exists - simulate successful ping
        return {
            "target": target,
            "ip": device_data["ip"],
            "packets_sent": count,
            "packets_received": count,
            "packet_loss": 0,
            "rtt_min": 0.5,
            "rtt_avg": 1.2,
            "rtt_max": 2.1,
            "status": "reachable"
        }
    
    # Unknown target - simulate timeout
    return {
        "target": target,
        "packets_sent": count,
        "packets_received": 0,
        "packet_loss": 100,
        "status": "unreachable",
        "error": "Destination host unreachable"
    }


def execute_command(device: str, command: str) -> str:
    """
    Execute a show command on a device (mock implementation).
    
    Args:
        device: Device hostname
        command: Command to execute (must start with 'show')
    
    Returns:
        Command output as string
    """
    device_data = MockNetworkDevice.get_device_data(device)
    
    if not device_data:
        return f"Error: Device '{device}' not found"
    
    # Security: Only allow show commands
    if not command.strip().lower().startswith("show"):
        return "Error: Only 'show' commands are allowed for security reasons"
    
    # Simulate specific commands
    if "show version" in command.lower():
        return f"""Arista {device_data['model']}
Hardware version: {device_data['model']}
Serial number: {device_data['serial']}
Software image version: {device_data['version']}
Uptime: {device_data['uptime_days']} days
"""
    
    elif "show ip interface brief" in command.lower():
        output = "Interface         IP Address      Status    Protocol\n"
        for name, data in device_data["interfaces"].items():
            ip = "unassigned" if "Management" not in name else device_data["ip"]
            output += f"{name:<17} {ip:<15} {data['status']:<9} {data['status']}\n"
        return output
    
    elif "show ip bgp summary" in command.lower():
        bgp = device_data["bgp"]
        output = f"BGP router identifier {bgp['router_id']}, local AS number {bgp['local_as']}\n"
        output += "\nNeighbor        AS      State       Uptime    Prefixes\n"
        for n in bgp["neighbors"]:
            output += f"{n['ip']:<15} {n['remote_as']:<7} {n['state']:<11} {n['uptime']:<9} {n['prefixes']}\n"
        return output
    
    else:
        return f"Command '{command}' not implemented in mock device.\nAvailable: show version, show ip interface brief, show ip bgp summary"


def get_topology_info() -> Dict:
    """
    Get information about the network topology.
    
    Returns:
        Dict with topology structure
    """
    return {
        "name": "Spine-Leaf Topology",
        "type": "2-spine, 2-leaf",
        "devices": {
            "spines": ["spine1", "spine2"],
            "leaves": ["leaf1", "leaf2"]
        },
        "links": [
            {"from": "spine1", "to": "leaf1", "interface": "Ethernet1"},
            {"from": "spine1", "to": "leaf2", "interface": "Ethernet2"},
            {"from": "spine2", "to": "leaf1", "interface": "Ethernet1"},
            {"from": "spine2", "to": "leaf2", "interface": "Ethernet2"},
            {"from": "spine1", "to": "spine2", "interface": "Ethernet3"}
        ],
        "management_network": "192.168.0.0/24",
        "underlay_protocol": "BGP",
        "overlay_protocol": "EVPN"
    }


# Demo/test function
if __name__ == "__main__":
    print("🌐 Mock Network Device Simulator")
    print("="*70)
    print("\nAvailable devices:", MockNetworkDevice.list_devices())
    print("\n" + "="*70)
    
    # Test device status
    print("\n📊 Device Status:")
    print("-"*70)
    for device in ["spine1", "leaf1"]:
        status = get_device_status(device)
        print(f"\n{device}:")
        print(f"  Status: {status.get('status')}")
        print(f"  Version: {status.get('version')}")
        print(f"  Uptime: {status.get('uptime')}")
    
    # Test BGP summary
    print("\n" + "="*70)
    print("\n🔀 BGP Summary:")
    print("-"*70)
    bgp = get_bgp_summary("spine1")
    print(f"\nDevice: {bgp['device']}")
    print(f"Local AS: {bgp['local_as']}")
    print(f"Peers: {bgp['established_peers']}/{bgp['total_peers']} established")
    
    # Test interface status
    print("\n" + "="*70)
    print("\n🔌 Interface Status:")
    print("-"*70)
    intf = get_interface_status("leaf2", "Ethernet3")
    print(f"\nInterface: {intf.get('interface')}")
    print(f"Description: {intf.get('description')}")
    print(f"Status: {intf.get('status')}")
    print(f"Speed: {intf.get('speed')}")
    
    # Test ping
    print("\n" + "="*70)
    print("\n📡 Ping Test:")
    print("-"*70)
    ping_result = ping_device("spine1")
    print(f"\nTarget: {ping_result['target']}")
    print(f"Status: {ping_result['status']}")
    print(f"Packet Loss: {ping_result['packet_loss']}%")
    
    print("\n" + "="*70)
    print("✅ All mock functions working!")
    print("="*70)
