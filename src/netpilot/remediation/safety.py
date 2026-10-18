"""Fail-closed P0 catalog policy. Nothing in this module executes instructions."""
import re

_DANGEROUS = re.compile(
    r"(?i)invoke[-\s]*expression|\biex\b|\biwr\b|curl\s*[^\n]*\|\s*(?:sh|bash)|"
    r"invoke-command|enter-pssession|start-process|runas|execution\s*policy|executionpolicy|"
    r"winsock|netsh\s+.*(?:reset|set|delete)|set-dns|set-net|route\s+(?:delete|add|change)|"
    r"reg\s+(?:add|delete)|set-itemproperty|restart-service|stop-service|"
    r"\bsudo\b|\brm\s+-(?:rf|fr)|format-volume|remove-netroute|disable-netadapter|"
    r"set-netfirewall|bcdedit|python\s+-c|encodedcommand|"
    r"关闭.{0,24}(?:防火墙|杀毒|安全|firewall|antivirus)|禁用.{0,24}(?:防火墙|安全|firewall)|删除.{0,8}(?:驱动|路由)|"
    r"卸载.{0,8}(?:网卡|设备)|重置.{0,8}(?:网络栈|整个网络)|修改注册表|管理员提权|"
    r"(?:静态|手工).{0,6}(?:设置|修改).{0,5}dns"
)


def validate_template(template):
    if template.risk != "low" or template.requires_admin:
        raise ValueError("P0 only permits low-risk non-admin actions")
    if not template.instructions or not all(item.strip() for item in template.instructions) or not template.verification.strip():
        raise ValueError("instructions and verification are required")
    if template.changes_system_state and (not template.reversible or not template.rollback_instructions):
        raise ValueError("P0 changes require reversibility and rollback")
    # Static prose/templates only. No commands, interpolation or downloaded code.
    for text in (template.title, *template.instructions, *template.rollback_instructions, template.verification):
        if _DANGEROUS.search(text):
            raise ValueError("dangerous instructions are not approved")
        if re.search(r"\{\{|\$\(|\$\{|`|https?://|\b(?:powershell|cmd\.exe|bash\s+-c)\b", text, re.I):
            raise ValueError("commands, URLs and interpolation are not permitted in P0 templates")
    return template


def validate_catalog(catalog):
    for key, template in catalog.items():
        if key != template.template_id:
            raise ValueError("catalog key mismatch")
        validate_template(template)
