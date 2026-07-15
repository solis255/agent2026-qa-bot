# Tool inventory and safety matrix

List every tool before exposing it to the model.

| Tool | Purpose | Inputs | Output shape | Safety rule |
|---|---|---|---|---|
| `device_status(device)` | Return inventory and health for one known device | `device` | structured status object | Reject unknown devices |
| `interface_status(device, interface=None)` | Return one interface or all interfaces for a device | `device`, optional `interface` | interface list or object | Validate device and optional interface |
| `bgp_summary(device)` | Return BGP peer state and prefix counts | `device` | BGP summary object | Validate device and return structured errors |
| `ping(target, count=4)` | Run bounded reachability checks | `target`, `count` | reachability result | Limit count and reject unsafe targets |
| `show_command(device, command)` | Run approved read-only show commands | `device`, `command` | command result | Allowlist commands and block configuration mode |
| `topology()` | Return known topology relationships | none | topology object | Return static or approved inventory data only |
