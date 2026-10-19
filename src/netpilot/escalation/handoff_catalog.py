"""Static read-only human investigation suggestions, never production changes."""


def handoff_checks(categories=(), *, mock=False):
    checks = ["核对受影响设备、发生时间与影响范围；确认同接入网络、AP 或 VLAN 是否有共性问题。",
              "由授权人员核验校园认证会话与平台状态；NetPilot 未访问校园内部运维平台。"]
    if any("dns" in c.casefold() or "network" in c.casefold() for c in categories):
        checks += ["核对客户端 DNS / DHCP 配置与当前接入策略是否一致。",
                   "由授权人员核对故障时段 DNS 服务可用性及相关解析日志，区分客户端、代理与上游解析路径。"]
    if any(any(k in c for k in ("tcp", "http", "gateway", "ping")) for c in categories):
        checks.append("只读核验网关、出口与代理访问策略及对应日志；不据单次失败推定 ACL 或服务端根因。")
    if mock: checks.insert(0, "本材料来自 Mock 模拟终端，仅用于演示；不得据此处理真实校园网络。")
    return tuple(checks)
