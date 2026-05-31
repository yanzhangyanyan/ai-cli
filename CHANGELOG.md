# Changelog

All notable changes to aiCLI will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-05-31

### Added
- AI-powered autonomous command execution via natural language
- Three execution scenarios: local machine, remote Linux, remote Windows
- Dual mode: standalone CLI + MCP Server (9 tools)
- ReAct loop: Think → Act → Observe → self-heal on errors
- Safety net: code-level forced confirmation for dangerous commands
- Cross-platform probe: auto-detects Windows/Linux/macOS
- Context memory: set project context, agent remembers across tasks
- Smart compression: auto-summarizes long task history
- Bilingual UI: English and Chinese, selectable on first run
- SSH connection diagnostics with installation guidance
- sudo password support with real-time stdin injection
- Ctrl+C pause/resume (never accidentally exits)
- LocalConnector for zero-dependency local execution
- SSHConnector with Windows target support and binary-safe output
- OpenAI-compatible API support (OpenAI, GLM, Ollama, LiteLLM, etc.)
- Config wizard on first run with model auto-discovery
