---
title: 天津大学校园网 IPv6 使用及配置方法（Windows XP/Vista）
source: https://its.tju.edu.cn/info/1158/1102.htm
source_type: official
retrieved_at: 2026-09-30
---

# 资料属性

本文件根据天津大学信息与网络中心发布的《IPv6 使用及配置方法》整理。原页面发布日期为 2023 年 4 月 2 日，本文件于 2026 年 9 月 30 日核对。

原页面只介绍 Windows XP 和 Windows Vista，属于面向旧版操作系统的历史配置资料，不应直接作为 Windows 10、Windows 11、macOS、Linux、手机或路由器的通用配置指南。网络环境、IPv6 地址前缀和测试方法可能已经调整，实际使用时应以天津大学信息与网络中心最新说明为准。

# 适用条件

原页面说明，以下配置需要在计算机单机直连校园网的情况下进行。通过路由器、共享网络、虚拟机或其他中间设备连接时，获取 IPv6 地址的结果可能不同。

可供检索的关键词包括：天津大学 IPv6、校园网 IPv6、IPv6 地址、IPv6 配置、IPv6 测试、Windows XP IPv6、Windows Vista IPv6、单机直连。

# Windows XP 配置

## 1. 安装 IPv6 协议栈

在 Windows XP 中安装 IPv6 协议栈。

## 2. 查看 IPv6 地址

查看计算机获取到的 IPv6 地址。原页面要求地址以 `2001:da8:a000:` 开头；该前缀具有时效性，如当前地址不符合，应先核对学校最新网络说明，不要仅凭旧前缀判断网络一定异常。

## 3. 测试 IPv6 协议栈

按原页面示例测试 IPv6 协议栈及连通性。

## 4. 重新获取 IPv6 地址

原页面说明，断网时可在 Windows XP 环境中执行 `ipv6 renew`，尝试重新获取 IPv6 地址。该命令针对旧版 Windows，不适用于所有现代操作系统。

# Windows Vista 配置

## 1. 启用 IPv6 协议

原页面说明，可按与 Windows XP 类似的方式安装 IPv6，并使用 `ipv6 if` 查看 IPv6 地址。配置过程中需要确认网络连接属性中的“Internet 协议版本 6（TCP/IPv6）”已勾选。

## 2. 确认 IPv6 地址

启用协议后，确认计算机是否正确获取 IPv6 地址。

# 使用限制与故障处理

如果使用现代操作系统、无法获取 IPv6 地址或无法访问 IPv6 网站，不要照搬 Windows XP/Vista 命令。可先确认设备是否单机直连、系统是否已启用 TCP/IPv6，并向天津大学信息与网络中心咨询当前的 IPv6 地址范围和配置方法。排障时不要提供校园网密码、Cookie 或其他登录凭据。
