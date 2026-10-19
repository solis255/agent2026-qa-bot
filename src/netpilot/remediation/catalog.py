"""Immutable, version-controlled P0 action templates. No runtime downloads."""
from types import MappingProxyType
from typing import Literal
from pydantic import BaseModel, ConfigDict


class RemediationTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    template_id: str
    equivalence_key: str
    issue_types: tuple[str, ...]
    title: str
    applicable_os: tuple[str, ...] = ("any",)
    applicable_targets: tuple[str, ...] = ("user_client", "netpilot_host", "mock_client")
    applicable_network_access: tuple[str, ...] = ("any",)
    risk: Literal["low", "medium", "high"] = "low"
    requires_admin: bool = False
    changes_system_state: bool = False
    reversible: bool = True
    instructions: tuple[str, ...]
    rollback_instructions: tuple[str, ...] = ()
    verification: str
    verification_metrics: tuple[str, ...] = ("dns_resolution", "gateway_reachability", "tcp_connectivity", "http_reachability", "network_configuration", "user_observed_symptom")
    prerequisites: tuple[str, ...] = ()
    priority: int = 10


def template(key, title, issues, instructions, verification, **kwargs):
    return RemediationTemplate(template_id=key, equivalence_key=kwargs.pop("equivalence_key", key),
                               title=title, issue_types=issues, instructions=instructions,
                               verification=verification, **kwargs)


CATALOG = MappingProxyType({item.template_id: item for item in (
    template("confirm_scope", "确认影响范围与当前状态", ("unknown", "web_only"),
             ("确认问题影响所有应用还是单个网站，记录出现时间与可见错误。", "只查看状态，不更改网络或安全设置。"),
             "确认可重现的问题范围；信息不足时先补充现象。", priority=10),
    template("check_link", "查看当前连接状态", ("gateway_connectivity", "unknown"),
             ("查看当前 Wi-Fi 是否连接或网线接口指示状态；不拆卸设备或更改配置。",),
             "确认是否连接到预期网络；不据此断言互联网正常。", priority=15),
    template("reopen_browser", "保存内容后重新打开应用", ("dns", "web_only", "single_service"),
             ("先保存浏览器或受影响应用中的未提交内容。", "关闭受影响应用后重新打开，再尝试原先失败的页面或服务。"),
             "手动重试原先失败的操作，记录是否改善。", changes_system_state=True,
             rollback_instructions=("重新打开原应用与保存的页面；不要清除浏览记录或用户数据。",), priority=20),
    template("reopen_service", "仅重新打开受影响服务", ("single_service",),
             ("保存受影响应用的内容，只关闭并重新打开该应用。", "保持其他正常应用和网络连接不变。"),
             "重试同一服务，确认其他应用是否仍正常。", changes_system_state=True,
             rollback_instructions=("重新打开原应用及已保存内容。",), priority=20),
    template("check_service_status", "核验服务状态与访问条件", ("single_service",),
             ("通过你已核验的服务状态渠道确认是否维护。", "确认该资源是否要求校园内访问或 VPN，不猜测特定入口或账号规则。"),
             "明确是服务维护、访问条件限制还是仍需补充证据。", priority=10),
    template("confirm_vpn_proxy", "确认 VPN 与代理状态", ("vpn", "proxy", "unknown", "web_only", "dns"),
             ("查看你使用的 VPN / 代理应用状态；不知道时明确标为不确定。", "先确认是否有业务依赖，保持连接与防护现状不变。"),
             "记录已确认的开启、关闭或未知状态，不把 WinHTTP 当成全部浏览器代理。", priority=16),
    template("disconnect_vpn", "仅在不依赖 VPN 时临时断开对比", ("vpn", "web_only", "dns"),
             ("先确认当前业务不依赖 VPN，且不会影响远程管理；否则跳过。", "仅使用原 VPN 应用的断开按钮短暂对比普通公网网页；不要修改 VPN 配置。"),
             "手动重试同一普通公网页面并记录差异；内网资源不适用。", changes_system_state=True,
             rollback_instructions=("使用原 VPN 应用重新连接原连接，恢复先前状态。",), prerequisites=("vpn_true_public",), priority=35),
    template("pause_proxy", "仅在不依赖代理时临时暂停对比", ("proxy", "web_only"),
             ("确认当前业务不依赖代理，且不会影响远程管理；否则跳过。", "只使用原代理应用的暂停按钮对比普通公网页面，不更改系统代理配置。"),
             "重试同一页面并记录差异，不把变化直接认定为唯一根因。", changes_system_state=True,
             rollback_instructions=("在原代理应用恢复先前的启用状态。",), prerequisites=("proxy_true_public",), priority=36),
    template("reconnect_network", "重新连接当前网络", ("dns", "gateway_connectivity"),
             ("先保存工作，确认短暂断网不会中断会议、远程控制或重要传输；有依赖则跳过。", "使用系统界面断开当前连接，等待数秒后重新连接原网络；不修改 DNS、路由或网卡属性。"),
             "手动重新访问此前失败的页面或服务，记录结果。", changes_system_state=True,
             rollback_instructions=("通过系统界面重新连接原网络，保持原自动获取参数设置；无法恢复时停止并联系维护者。",), priority=30),
    template("campus_reconnect", "重新连接原校园网络", ("dns", "gateway_connectivity", "campus_auth"),
             ("先保存工作并确认短暂断网不会影响重要业务或远程管理；否则跳过。", "通过系统界面重新连接原校园网络，不改变接入参数或网卡配置。"),
             "查看连接状态并手动重试原页面。", changes_system_state=True,
             rollback_instructions=("重新连接先前的校园网络，保留原设置；不能恢复时停止。",),
             applicable_network_access=("campus_wifi", "campus_wired"), equivalence_key="reconnect_network", priority=30),
    template("campus_reauthenticate", "必要时重新完成校园网认证", ("campus_auth", "dns", "gateway_connectivity"),
             ("仅在确实显示未认证或认证失效时操作，否则跳过。", "使用你已核验的学校认证入口重新完成认证；不要向 NetPilot 提供密码，不猜测入口或账号规则。"),
             "确认认证界面的结果，再手动重试原服务。", changes_system_state=True,
             rollback_instructions=("保留原网络设置；如需退出，仅使用原认证界面的正常退出方式，不修改账号或接入配置。",),
             applicable_network_access=("campus_wifi", "campus_wired"), prerequisites=("auth_suspected",), priority=40),
    template("check_official_guide", "核验学校或维护者说明", ("campus_auth", "dns", "vpn", "proxy"),
             ("先核验所引用资料的来源与时效，校园特定入口和账号规则以学校或维护者说明为准。", "若仅有社区资料，先向官方核验，不直接据其修改配置。"),
             "确认适用说明后再决定是否操作；无法核验则停止。", prerequisites=("campus_sources",), priority=18),
    template("record_and_escalate", "保留现象并反馈维护者", ("dns", "gateway_connectivity", "campus_auth", "vpn", "proxy", "web_only", "single_service", "unknown"),
             ("记录错误现象、发生时间及已经尝试的步骤与结果。", "如仍未改善，向可信维护者反馈最小必要摘要；不提供密码、Cookie、密钥或完整设备标识。"),
             "记录问题是否仍存在；本步骤不代表故障已经解决。", priority=50),
)})
