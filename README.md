<p align="center">
  <img src="assets/logo.png" alt="aiCLI Logo" width="400">
</p>

# aiCLI — AI-Powered Command Line Agent

> **You speak, it executes.** Describe what you want in natural language — aiCLI plans the steps, runs the commands, and handles errors autonomously.

<p align="center">
  <strong>爱 CLI</strong> — Because nobody remembers all those commands.
</p>

---

## Sound Familiar?

- 😤 Can't remember the exact `grep`/`awk`/`sed` flags to extract that field?
- 😤 Every time you install software, you Google the tutorial? Docker, Nginx, MySQL — all different?
- 😤 Staring at the terminal, unsure what command to type next?
- 😤 You're great at Java/Python/Frontend, but Linux sysadmin is not your thing?

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
pip install aicli
# or
uv tool install aicli

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
| **Sudo Support** | Detects sudo password prompts in real-time, injects via stdin |
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

**MCP Tools available**: `aicli_task`, `aicli_local_task`, `aicli_connect`, `aicli_exec`, `aicli_file_read`, `aicli_file_write`, `aicli_probe`, `aicli_disconnect`, `aicli_list_sessions`

### CLI Commands

```
# Connection
local                               Local mode (no SSH needed)
connect <user@host> [password]      Connect to remote host
disconnect                          Disconnect

# Operations
exec <command>                      Execute a single command manually
file_read <path>                    Read a file
file_write <path> <content>         Write to a file
probe                               Detect system info

# AI Tasks
run <description>                   Agent plans and executes
<free text>                         Just type what you want (same as run)

# Configuration
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

| Priority | Method | Example |
|----------|--------|---------|
| 1 (highest) | CLI args | `aicli --llm http://localhost:4000/v1 --model gpt-4o` |
| 2 | Environment vars | `AICLI_LLM_BASE_URL`, `AICLI_LLM_API_KEY`, `AICLI_LLM_MODEL` |
| 3 | Config file | `~/.config/aicli/config.json` |

### Config File

```json
{
  "base_url": "https://api.openai.com/v1",
  "api_key": "sk-...",
  "model": "gpt-4o",
  "thinking": false
}
```

### Supported LLM Providers

Any OpenAI-compatible API:

| Provider | Base URL | Notes |
|----------|----------|-------|
| OpenAI | `https://api.openai.com/v1` | GPT-4o, etc. |
| GLM (Zhipu) | `https://open.bigmodel.cn/api/paas/v4` | GLM-4, GLM-5 |
| Ollama (local) | `http://localhost:11434/v1` | Any local model |
| LiteLLM (proxy) | `http://localhost:4000/v1` | Unified gateway |

## Architecture

```
User: "Install Docker and deploy Nginx"
         ↓
    ┌─────────────────────────────┐
    │         aiCLI Agent         │
    │                             │
    │  1. Plan (LLM)              │
    │     → 4 steps, risk levels  │
    │                             │
    │  2. Execute (ReAct loop)    │
    │     → Think → Act → Observe │
    │     → Error? → Replan       │
    │                             │
    │  3. Safety Net (code-level)  │
    │     → rm -rf? → FORCE CONFIRM│
    └─────────┬───────────────────┘
              ↓
    ┌─────────────────┐
    │    Connector     │
    ├─────────────────┤
    │ LocalConnector   │  ← subprocess (no SSH)
    │ SSHConnector     │  ← asyncssh (Linux/Win/Mac)
    └─────────────────┘
```

## How It Works

1. **You describe the task** in natural language
2. **aiCLI plans** a complete step-by-step execution plan
3. **You confirm** (or adjust) the plan
4. **aiCLI executes** each step autonomously:
   - Low-risk → auto-execute (install software, check status)
   - High-risk → ask for confirmation (delete files, restart services)
5. **Errors?** aiCLI analyzes the error and tries an alternative approach
6. **Done!** Summary of what was accomplished

## Installation

### From PyPI (coming soon)

```bash
pip install aicli
```

### From Source

```bash
git clone https://github.com/chzy40307891/aicli.git
cd aicli
uv sync
uv run aicli --local
```

## Development

```bash
git clone https://github.com/chzy40307891/aicli.git
cd aicli
uv sync

# Run tests
uv run python -c "from aicli.connectors.local import LocalConnector; print('OK')"

# Run locally
uv run aicli --local
```

## License

MIT License — use it however you want.

---

<p align="center">
  <strong>aiCLI</strong> — 爱CLI<br>
  Because commands should understand <em>you</em>, not the other way around.
</p>
