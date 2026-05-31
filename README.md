<p align="center">
  <img src="assets/logo.png" alt="aiCLI Logo" width="400">
</p>

# aiCLI — AI-Powered Command Line Agent

> **You speak, it executes.** Describe what you want in natural language — aiCLI plans the steps, runs the commands, and handles errors autonomously.

<p align="center">
  <strong>爱 CLI</strong> — Because nobody remembers all those commands.<br>
  <strong>爱 CLI</strong> — 因为没人记得住那么多命令。
</p>

<p align="center">
  <a href="#english">English</a> | <a href="#中文">中文</a>
</p>

---

<a id="english"></a>

## 😤 Sound Familiar?

- Can't remember the exact `grep`/`awk`/`sed` flags to extract that field?
- Every time you install software, you Google the tutorial? Docker, Nginx, MySQL — all different?
- Staring at the terminal, unsure what command to type next?
- You're great at Java/Python/Frontend, but Linux sysadmin is not your thing?

**aiCLI is built for developers who just want to get things done — without memorizing a thousand commands.**

```
$ aicli --local
aicli> install Docker and Docker Compose

==================================================
  1. Check existing Docker installation — 5s — safe
  2. Install Docker Engine — 60s — low risk
  3. Install Docker Compose plugin — 30s — low risk
  4. Verify installation — 5s — safe
==================================================

  Confirm execution plan? [Y]: Y

──────────────────────────────────────────────────
  Step 1
  GOAL:  Check if Docker is already installed
  CMD:   docker --version
  RISK:  safe *  [auto-execute]
──────────────────────────────────────────────────
[auto] executing...
[OK] | 200ms

  ... (aiCLI continues through all steps autonomously)

==================================================
[DONE] | 4 commands executed
       Docker v27.3.1 and Docker Compose v2.29.7 installed successfully
```

## Three Scenarios, One Tool

| Scenario | Command | Description |
|----------|---------|-------------|
| **Local Machine** | `aicli --local` | Execute commands on your own computer |
| **Remote Linux** | `aicli --host 192.168.1.100 --user root` | SSH into any Linux server |
| **Remote Windows** | `aicli --host 10.0.0.5 --user administrator` | SSH into Windows (OpenSSH Server required) |

## Quick Start

```bash
# Install
pip install ai-cli
# or
uv tool install ai-cli

# Run (first run auto-configures LLM)
aicli --local
```

### Prerequisites

| Dependency | Version | Notes |
|-----------|---------|-------|
| Python | ≥ 3.11 | Runtime |
| LLM API | Any OpenAI-compatible | ChatGPT, GLM, Ollama, LiteLLM, etc. |

## Features

| Feature | Description |
|---------|-------------|
| **Natural Language → Execution** | Describe what you want, aiCLI plans and executes |
| **Autonomous Planning** | Receives task → outputs full plan → confirms → executes step by step |
| **Auto / Confirm Modes** | Low-risk operations auto-execute; high-risk operations ask first |
| **Error Self-Healing** | If a step fails, aiCLI analyzes the error and tries an alternative |
| **Safe by Design** | Code-level safety net: `rm -rf`, `mkfs`, `reboot` always require confirmation |
| **Cross-Platform** | Local (Windows/Linux/macOS), Remote Linux, Remote Windows |
| **Dual Mode** | Standalone CLI + MCP Server (embed into any AI agent) |
| **Context Memory** | Set project context; agent remembers across tasks |
| **Smart Compression** | 200-step long tasks auto-summarize early steps to stay within token limits |
| **Bilingual** | English and Chinese UI — select on first run |
| **Connection Diagnostics** | If SSH fails, tells you exactly why and how to fix it |

## Usage

### Interactive CLI

```bash
# Local mode
aicli --local

# Remote SSH
aicli --host 192.168.1.100 --user root --password secret

# With options
aicli --local --llm https://api.openai.com/v1 --model gpt-4o
```

### Inside aiCLI

```
aicli> install nginx

aicli> check disk space and clean up /tmp if over 80%

aicli> configure UFW firewall: allow 80, 443, deny 3306

aicli> deploy this docker-compose.yml and make sure all containers are healthy
```

### MCP Server Mode

aiCLI can be embedded into any MCP-compatible AI agent (opencode, Claude Desktop, etc.):

```json
{
  "mcpServers": {
    "aicli": {
      "type": "local",
      "command": ["aicli", "serve"],
      "environment": {
        "AICLI_LLM_BASE_URL": "https://api.openai.com/v1",
        "AICLI_LLM_API_KEY": "sk-...",
        "AICLI_LLM_MODEL": "gpt-4o"
      },
      "timeout": 60000
    }
  }
}
```

### CLI Commands

```
local                               Local mode (no SSH needed)
connect <user@host> [password]      Connect to remote host
disconnect                          Disconnect
exec <command>                      Execute a single command manually
file_read <path>                    Read a file
file_write <path> <content>         Write to a file
probe                               Detect system info
run <description>                   Agent plans and executes
<free text>                         Just type what you want (same as run)
config                              View config
config model [name]                 Switch model
config thinking [on|off]            Toggle thinking mode
config setup                        Reconfigure wizard
context <description>               Set project context
```

## Configuration

### Config Priority

```
CLI args (--llm, --model)  >  Environment vars (AICLI_LLM_*)  >  Config file
```

### Supported LLM Providers

Any OpenAI-compatible API:

| Provider | Base URL | Notes |
|----------|----------|-------|
| OpenAI | `https://api.openai.com/v1` | GPT-4o, etc. |
| GLM (Zhipu) | `https://open.bigmodel.cn/api/paas/v4` | GLM-4, GLM-5 |
| Ollama (local) | `http://localhost:11434/v1` | Any local model |
| LiteLLM (proxy) | `http://localhost:4000/v1` | Unified gateway |

## Installation

### From Source

```bash
git clone https://github.com/yanzhangyanyan/ai-cli.git
cd aicli
uv sync
uv run aicli --local
```

## License

GNU Affero General Public License v3.0 (AGPL-3.0) — free to use and modify, but all derivative works must also be open source. Cloud service providers using modified versions must provide source code to users.

---
---

<a id="中文"></a>

## 😤 是不是很熟悉？

- 记不住 `grep`/`awk`/`sed` 的各种参数组合？
- 每次装软件都要搜教程？Docker、Nginx、MySQL 配置各不同？
- 对着终端发呆，不知道下一步该敲什么？
- Java/前端写得溜，但 Linux 命令行是你的噩梦？

**aiCLI 专为"只想把活干完，不想背一千条命令"的开发者而生。**

```
$ aicli --local
aicli> 安装 Docker 和 Docker Compose

==================================================
  1. 检查现有 Docker 安装 — 5s — 安全
  2. 安装 Docker Engine — 60s — 低风险
  3. 安装 Docker Compose 插件 — 30s — 低风险
  4. 验证安装 — 5s — 安全
==================================================

  确认执行此方案？[Y]: Y

──────────────────────────────────────────────────
  Step 1
  GOAL:  检查是否已安装 Docker
  CMD:   docker --version
  RISK:  安全 *  [自动执行]
──────────────────────────────────────────────────
[auto] executing...
[OK] | 200ms

  ... （aiCLI 自动继续执行后续步骤）

==================================================
[DONE] | 4 commands executed
       Docker v27.3.1 和 Docker Compose v2.29.7 安装成功
```

## 三个场景，一个工具

| 场景 | 命令 | 说明 |
|------|------|------|
| **本机执行** | `aicli --local` | 在你自己的电脑上智能执行命令，无需 SSH |
| **远程 Linux** | `aicli --host 192.168.1.100 --user root` | SSH 连接任意 Linux 服务器 |
| **远程 Windows** | `aicli --host 10.0.0.5 --user administrator` | SSH 连接 Windows（需安装 OpenSSH Server） |

## 快速开始

```bash
# 安装
pip install ai-cli
# 或者
uv tool install ai-cli

# 运行（首次运行自动配置 LLM，支持中文界面）
aicli --local
```

### 前提条件

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | ≥ 3.11 | 运行时 |
| LLM API | 任何 OpenAI 兼容接口 | ChatGPT、智谱 GLM、Ollama、LiteLLM 等 |

## 核心特性

| 特性 | 说明 |
|------|------|
| **自然语言 → 自动执行** | 说人话，aiCLI 自动规划并执行 |
| **自主规划** | 收到任务后输出完整方案，确认后逐步执行 |
| **自动/确认模式** | 低风险操作自动执行，高风险操作需确认 |
| **错误自修复** | 步骤失败时自动分析原因，换方案重试 |
| **安全设计** | 代码层安全网：`rm -rf`、`mkfs`、`reboot` 强制确认 |
| **跨平台** | 本机（Windows/Linux/macOS）、远程 Linux、远程 Windows |
| **双模式** | 独立 CLI + MCP Server（可嵌入任意 AI 智能体） |
| **上下文记忆** | 设置项目上下文，跨任务记忆不丢失 |
| **智能压缩** | 200 步长任务自动摘要，不爆 token |
| **中英双语** | 首次运行选择语言，全程中文/英文界面 |
| **连接诊断** | SSH 失败时告诉你原因和修复方法 |

## 使用方法

### 交互式 CLI

```bash
# 本机模式
aicli --local

# 远程 SSH
aicli --host 192.168.1.100 --user root --password 密码

# 指定 LLM
aicli --local --llm https://api.openai.com/v1 --model gpt-4o
```

### 在 aiCLI 内部

```
aicli> 安装 nginx

aicli> 检查磁盘空间，超过 80% 就清理 /tmp

aicli> 配置防火墙：放行 80、443，拒绝 3306

aicli> 部署 docker-compose.yml，确保所有容器健康运行
```

### MCP Server 模式

aiCLI 可以嵌入任何支持 MCP 协议的 AI 智能体（opencode、Claude Desktop 等）：

```json
{
  "mcpServers": {
    "aicli": {
      "type": "local",
      "command": ["aicli", "serve"],
      "environment": {
        "AICLI_LLM_BASE_URL": "https://api.openai.com/v1",
        "AICLI_LLM_API_KEY": "sk-...",
        "AICLI_LLM_MODEL": "gpt-4o"
      },
      "timeout": 60000
    }
  }
}
```

### CLI 命令

```
local                               本机模式（无需 SSH）
connect <user@host> [密码]          连接远程主机
disconnect                          断开连接
exec <命令>                         手动执行单条命令
file_read <路径>                    读取文件
file_write <路径> <内容>            写入文件
probe                               探测系统信息
run <任务描述>                      Agent 规划并执行
<自然语言>                          直接输入（等同于 run）
config                              查看配置
config model [名称]                 切换模型
config thinking [on|off]            切换思考模式
config setup                        重新配置向导
context <描述>                      设置项目上下文
```

## 配置

### 配置优先级

```
命令行参数 (--llm, --model)  >  环境变量 (AICLI_LLM_*)  >  配置文件
```

### 支持的 LLM

任何 OpenAI 兼容 API：

| 提供商 | 地址 | 说明 |
|--------|------|------|
| OpenAI | `https://api.openai.com/v1` | GPT-4o 等 |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | GLM-4、GLM-5 |
| Ollama（本地） | `http://localhost:11434/v1` | 任意本地模型 |
| LiteLLM（代理） | `http://localhost:4000/v1` | 统一网关 |

## 从源码安装

```bash
git clone https://github.com/yanzhangyanyan/ai-cli.git
cd aicli
uv sync
uv run aicli --local
```

## 许可证

GNU Affero General Public License v3.0 (AGPL-3.0) — 自由使用和修改，但所有衍生作品必须开源。云服务商使用修改版本必须向用户提供源代码。

---

<p align="center">
  <strong>aiCLI</strong> — 爱CLI<br>
  因为命令应该听懂<em>你</em>，而不是反过来。<br>
  Because commands should understand <em>you</em>, not the other way around.
</p>
