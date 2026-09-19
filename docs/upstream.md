# 上游来源与教学资源

本文集中保存原 README 中与 Packt 书籍配套工程相关的说明，使仓库根 [`README.md`](../README.md) 能以 TJU NetPilot 比赛产品为主线，同时不删除上游历史、教学入口、版权或 MIT attribution。

## Packt 上游说明

本仓库由 Packt 项目 [Building AI Agents for Network Operations](https://github.com/PacktPublishing/Building-AI-Agents-for-Network-Operations) 演进而来。上游内容以动手实验方式介绍网络运维 Agent，包括 LLM 基础、提示工程、结构化解析、带记忆 Chatbot、Agentic Tool Calling、MCP 和生产就绪模式。

在本仓库中：

- `src/netpilot/` 是 TJU NetPilot 正式产品代码；
- `web/`、`knowledge/`、产品相关 `scripts/` 和 `tests/` 服务于比赛应用；
- `labs/`、`lab/`、`examples/`、`bonus/`、`prompts/`、`docs/design-toolkit/` 主要是保留的上游教学资源；
- 教学目录名 `lab1-ollama` 和文件名 `agentic_network_bot_ollama.py` 为保持既有课程链接而保留，不代表 TJU NetPilot 正式运行时使用 Ollama；当前比赛模型术语统一为 `tju-llm`。

上游资源可以用于学习和复现实验，但不应被描述成 TJU NetPilot 的在线服务模块，也不表示产品拥有天津大学内部网络、设备或运维平台的访问权限。

## Chapter / Lab Map

| Chapter | 主要仓库资源 |
|---|---|
| Chapter 1: Understanding AI Agents for Network Operations | 概念章节，无强制 Lab |
| Chapter 2: LLM Fundamentals and Local Setup | `QUICKSTART.md`、`examples/temperature.py`、`labs/lab1-ollama/` |
| Chapter 3: Prompt Engineering for Network Automation | `labs/lab2-prompts/`、`prompts/` |
| Chapter 4: Parsing Network Outputs into Structured Data | `labs/lab1-ollama/challenge_*.py`、`examples/interface_output.json`、`examples/bgp_output.json` |
| Chapter 5: Building a Network Chatbot with Memory | `labs/lab3-chatbot/` |
| Chapter 6: Designing Tools and Agentic Workflows | `labs/lab4-agentic/agentic_network_bot_ollama.py`、`examples/mock_network_devices.py` |
| Chapter 7: Building the Main Network Troubleshooting Agent | `labs/lab4-agentic/agentic_network_bot_ollama.py`、`examples/mock_network_devices.py` |
| Chapter 8: From Lab Agents to Reusable Tools with MCP | `labs/lab5-mcp/` |
| Chapter 9: Moving Toward Production-Ready Network Agents | `labs/lab6-production-readiness/` |
| Appendix A: AI Network Agent Design Toolkit | `docs/design-toolkit/` |

Appendix A 的可复制工作表包括 use-case 评分、Tool Contract、安全矩阵、结构化输出、memory policy、运行手册和 go/no-go checklist。

## Labs 1–6

以下命令从仓库根目录运行，具体依赖和说明以各 Lab README 为准。它们是教学入口，不是启动 TJU NetPilot 正式应用的 Quick Start。

### Lab 1：LLM API 与结构化网络输出

目录：`labs/lab1-ollama/`

- 调用课程配置的 LLM 接口；
- 控制生成参数；
- 解析 JSON 输出；
- 练习接口、BGP、多厂商和错误处理挑战；
- `ssh/` 子目录包含可选的设备 SSH 版本。

```bash
python labs/lab1-ollama/simple_ollama_test.py
python labs/lab1-ollama/json_output_challenge.py
```

### Lab 2：Prompt Engineering

目录：`labs/lab2-prompts/`

- 使用 RACE 框架组织网络分析提示；
- 对网络配置和命令输出进行结构化解析；
- 复用 `PROMPT_TEMPLATES.md` 中的模板。

```bash
python labs/lab2-prompts/prompt_engineering_race.py
python labs/lab2-prompts/netmiko_config_parser.py
```

### Lab 3：带记忆的 Network Chatbot

目录：`labs/lab3-chatbot/`

- 对比 stateless 与 stateful Chatbot；
- 理解由应用保存并回传的 conversation history；
- 可选地连接教学网络设备进行只读 SSH 演示。

```bash
python labs/lab3-chatbot/chatbot_v1_stateless.py
python labs/lab3-chatbot/chatbot_v2_with_memory.py
```

### Lab 4：Agentic Network Bot

目录：`labs/lab4-agentic/`

- 定义网络检查 Tool；
- 让教学 Agent 获取设备状态、接口、BGP 与拓扑信息；
- 使用 `examples/mock_network_devices.py` 的 spine/leaf 数据；
- `lab4b_agentic_network_bot_netmiko.py` 是可选的 Netmiko 版本。

```bash
python labs/lab4-agentic/agentic_network_bot_ollama.py
```

### Lab 5：MCP

目录：`labs/lab5-mcp/`

- 将教学网络 Tool 暴露为 MCP server；
- 使用测试 client 验证 Tool；
- 通过简单 HTTP bridge 与静态 UI 理解服务边界。

```bash
python labs/lab5-mcp/client_test.py
python labs/lab5-mcp/mcp_server.py --sse
python labs/lab5-mcp/http_bridge.py
```

### Lab 6：Production Readiness

目录：`labs/lab6-production-readiness/`

- 练习安全 Tool 边界；
- 查看 production-oriented Agent skeleton；
- 使用 checklist 复核日志、错误、凭据、超时和审批等问题。

```bash
python labs/lab6-production-readiness/production_agent_skeleton.py
```

## Mock spine / leaf 教学拓扑

上游 Mock 数据位于 `examples/mock_network_devices.py`，模拟 Arista cEOS spine/leaf 网络，不需要真实设备或 Containerlab。

```text
spine1 (192.168.0.11) --+-- leaf1 (192.168.0.21)
                        +-- leaf2 (192.168.0.22)
spine2 (192.168.0.12) --+
```

教学数据中：

- `spine1`、`spine2` 和 `leaf1` 的 BGP peers 为 Established；
- `leaf2` 有一个 BGP neighbor 为 Idle；
- `leaf2` 的 `Ethernet3` 为 down；
- 示例只允许安全 `show` 命令的 mock execution。

这套 spine/leaf Mock 与正式产品的 `src/netpilot/tools/mock_network.py` 不是同一个 Provider。正式 NetPilot Mock 面向终端网络诊断，提供 `healthy`、`dns_failure`、`gateway_unreachable`、`tcp_ssh_blocked`、`http_failure`、`partial_connectivity` 六种场景。

## Containerlab 教学环境

`lab/` 保存可选的 Containerlab 资源：

```text
lab/
├── topology.clab.yml
└── configs/
    ├── leaf1.cfg
    ├── leaf2.cfg
    └── spine1.cfg
```

需要 Docker、Containerlab 与对应 Arista cEOS 镜像。部署和清理命令：

```bash
containerlab deploy -t lab/topology.clab.yml
containerlab destroy -t lab/topology.clab.yml --cleanup
```

相关可选 SSH 示例：

```bash
python scripts/03_connect_to_device.py leaf1
python scripts/04_get_interfaces.py leaf1
python labs/lab3-chatbot/chatbot_v3_live_ssh.py
python labs/lab4-agentic/lab4b_agentic_network_bot_netmiko.py
```

这些命令只用于用户明确搭建并授权的教学环境。TJU NetPilot 正式产品不会自动部署 Containerlab，也不会把教学设备当作天津大学真实网络。

## Bonus 与其他示例

- `bonus/lab-bun-chat/`：Bun + Ollama + memory 的额外 Chat UI 教学练习；与 TJU NetPilot Web/API 无运行时关系。
- `examples/temperature.py`、`tokens_test.py`、结构化 JSON：LLM 参数、Token 和解析示例。
- `prompts/`：提示工程材料。
- `docs/design-toolkit/`：面向读者的设计与运营模板。
- `QUICKSTART.md`：上游课程环境说明，根 README 的 NetPilot Quick Start 才是比赛产品入口。

## 教学用途与安全提示

上游 Labs 用于学习和受控实验。涉及 SSH、Containerlab 或网络设备时，只应在用户拥有授权的环境中运行；生产封装应保持只读 allowlist，不允许 `configure terminal`、`reload`、`copy`、`delete`、`write memory`、`bash` 等配置或破坏性命令。

教学示例的实现和安全强度不等同于 `src/netpilot/` 的正式产品边界。比赛评审、部署和测试应以根 README、`DESIGN.md`、`docs/architecture.md` 与 `tests/` 为准。

## 版权与 MIT Attribution

本仓库继续保留上游 [`LICENSE`](../LICENSE) 中的 MIT License 和版权声明：

- Copyright (c) 2026 Sif Baksh
- Copyright (c) 2026 Packt

MIT License 允许使用、复制、修改、合并、发布、分发、再许可和销售软件副本，但版权声明和许可声明必须包含在软件的所有副本或实质部分中。本次文档整理没有删除或替换上游版权。
