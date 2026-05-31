import json
import os
import platform
from pathlib import Path

_LANG = "en"

_MESSAGES = {
    "en": {
        "banner": "aiCLI v{version} — AI-Powered Command Line Agent",
        "banner_sub": "Describe what you want, it executes for you.\n",
        "llm_label": "LLM:   {model} [{mode}]",
        "api_label": "API:   {api}",
        "mode_label": "Mode:  Agent (auto-execute low risk, confirm high risk)",
        "config_hint": "config          View config | config model  Switch model",
        "context_hint": "context <desc>  Set project context",
        "help_hint": "help            All commands",
        "not_configured": "No LLM configuration found.\n",
        "setup_required": "aiCLI needs an LLM to work. Configure and restart.",
        "connecting": "... Connecting {user}@{host}:{port}...",
        "connected": "[OK] Connected | {os} | {cores} cores / {ram}GB / {disk}GB",
        "installed": "  Installed: {items}",
        "connect_failed": "[X] Connection failed: {error}",
        "port_unreachable": "\n  Port {port} is unreachable. Possible causes:",
        "cause_no_ssh": "    1. SSH service is not running on the target",
        "cause_firewall": "    2. Firewall is blocking port {port}",
        "cause_wrong_addr": "    3. Wrong IP address or port",
        "install_windows": "\n  If the target is Windows, install OpenSSH Server first:",
        "install_win_cmd1": "    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0",
        "install_win_cmd2": "    Start-Service sshd",
        "install_win_cmd3": "    Set-Service -Name sshd -StartupType Automatic",
        "install_linux": "\n  If the target is Linux:",
        "install_linux_cmd1": "    sudo apt install openssh-server   # Debian/Ubuntu",
        "install_linux_cmd2": "    sudo yum install openssh-server   # CentOS/RHEL",
        "install_linux_cmd3": "    sudo systemctl start sshd",
        "port_ok_auth": "\n  Port {port} is reachable but connection failed. Check credentials.",
        "already_connected": "Already connected. Disconnect first.\n",
        "not_connected": "Not connected.\n",
        "usage_connect": "Usage: connect <user@host[:port]> [password]\n",
        "usage_exec": "Usage: exec <command>\n",
        "usage_file_read": "Usage: file_read <path>\n",
        "usage_file_write": "Usage: file_write <path> <content>\n",
        "usage_run": "Usage: run <task description>\n",
        "disconnected": "[OK] {msg}\n",
        "context_set": "  [OK] Context set\n",
        "context_clear": "  [OK] Context cleared\n",
        "context_current": "  Current context: {ctx}\n",
        "local_connected": "[OK] Local mode | {os} | {cores} cores / {ram}GB",
        "lang_select": "Select language / 选择语言:",
        "lang_en": "  [1] English (default)",
        "lang_zh": "  [2] 中文",
        "lang_prompt": "Choice [1]: ",
        "lang_saved": "Language set to English.\n",
        "thinking": "  [thinking...]",
        "auto_exec": "  [auto] executing...",
        "confirm_exec": "  [Y]execute / [n]skip / [q]quit / <feedback>: ",
        "plan_confirm": "\n  Confirm execution plan? [Y/adjust]: ",
        "feedback": "  [feedback] adjusting...\n",
        "skipped": "  skipped\n",
        "aborted": "  [ABORT] task cancelled\n",
        "user_interrupt": "\n\n  ⏸ User interrupted (Ctrl+C)",
        "interrupt_choice": "  [r]retry / [k]kill / <feedback>: ",
        "byz": "bye",
        "unknown_cmd": "Unknown command: {cmd}. Type help for commands.\n",
        "not_connected_run": "Not connected. Use 'local' or 'connect' first.\n",
        "task_header": "\n{sep}\n  TASK: {task}\n{sep}\n",
        "done_header": "\n{sep}",
        "done_footer": "{sep}",
        "done_summary": "[DONE] | {count} commands executed (compressed {comp}x)",
        "step_header": "\n{sep}",
        "step_num": "  Step {n}",
        "step_think": "  THINK: {think}",
        "step_goal": "  GOAL:  {goal}",
        "step_cmd": "  CMD:   {cmd}",
        "step_risk": "  RISK:  {risk} {icon}  [{label}]",
        "result_ok": "\n[OK] | {ms}ms",
        "result_fail": "\n[X] (exit {code}) | {ms}ms",
        "stderr_label": "[stderr] {stderr}",
        "waiting": "\r  [waiting... {sec}s]",
        "ctrl_c_hint": "  [i] Ctrl+C does not quit aiCLI. Type quit/exit to leave.\n",
        "ctrl_c_exit": "\n  [!] 3 consecutive Ctrl+C, exiting",
        "sudo_prompt": "  [sudo] password: ",
        "compressed": "\n  [context compressed: {old} -> {new} msgs, {old_chars} -> {new_chars} chars]\n",
        "plan_title": "\n{sep}",
        "local_mode_label": "local",
        "help_text": """
aiCLI v{version} — AI-Powered Command Line Agent

LLM Configuration:
  config                              View current config
  config setup                        Reconfigure (wizard mode)
  config model [name]                 Switch model
  config thinking [on|off]            Toggle thinking mode
  config api                          Change API URL/key
  config reset                        Clear config

Connection:
  local                               Local mode (execute on this machine)
  connect <user@host[:port]> [pass]   Connect to remote host
  disconnect                          Disconnect
  sessions                            List connections

System:
  probe                               Detect system info

Operations:
  exec <command>                      Execute a single command manually
  file_read <path>                    Read remote file
  file_write <path> <content>         Write remote file

Context:
  context <description>               Set project context (Agent remembers it)
  context                             View current context
  context clear                       Clear context

AI Tasks:
  run <task description>              Agent plans and executes task
  <natural language>                  Type directly when connected (same as run)

Execution Control:
  [auto]           Agent auto-executes (low risk)
  [confirm] Y/Enter Confirm high-risk operations
         n         Skip current step
         q         Abort entire task
         <text>    Send as feedback to adjust plan
  Ctrl+C           Pause current task, give feedback to continue
  quit/exit         Exit aiCLI
""",
        "cli_help": """aiCLI v{version} — AI-Powered Command Line Agent

Usage:
  aicli                            Start interactive mode (auto-setup wizard on first run)
  aicli --local                    Local mode (execute on this machine)
  aicli config                     View LLM config
  aicli config setup               Reconfigure LLM (wizard)
  aicli config model [name]        Switch model
  aicli config thinking [on|off]   Toggle thinking mode
  aicli config api                 Change API URL/key
  aicli config reset               Clear config

Options:
  --host <host>       Auto-connect on startup
  --port <port>       SSH port (default 22)
  --user <user>       Username (default root)
  --password <pwd>    Password
  --local             Local mode
  --llm <url>         LLM API URL
  --model <model>     LLM model name
  --lang <en|zh>      Language (default en)

Config priority: CLI args > env vars > config file
Config file: {config_path}""",
        "setup_wizard_title": "  aicli first run — LLM setup wizard",
        "setup_wizard_desc": "  aicli needs an LLM API to work.\n  Supports any OpenAI-compatible API (LiteLLM / OpenAI / Zhipu / ...)",
        "setup_api_url": "  API URL [{default}]: ",
        "setup_api_key": "  API Key: ",
        "setup_fetching": "  Fetching available models...",
        "setup_connect_fail": "  Connection failed: {err}",
        "setup_manual": "  Enter model name manually (blank to cancel): ",
        "setup_cancelled": "  Setup cancelled.",
        "setup_manual_ok": "\n  OK model configured: {model}",
        "setup_config_saved": "  Config saved to: {path}",
        "setup_found": "  Found {count} models:",
        "setup_select": "  Select model number [1]: ",
        "setup_done": "\n  OK setup complete!",
        "setup_done_api": "     API:     {api}",
        "setup_done_model": "     Model:   {model}",
        "setup_done_path": "     Config:  {path}",
        "cfg_not_configured": "  Not configured. Run aicli to start setup wizard.",
        "cfg_api": "  API:      {api}",
        "cfg_model": "  Model:    {model}",
        "cfg_key": "  Key:      {key}",
        "cfg_thinking": "  Thinking: {status}",
        "cfg_file": "  File:     {path}",
        "cfg_model_switched": "  OK model switched to: {model}",
        "cfg_no_api": "  API not configured. Run aicli config setup first.",
        "cfg_fetch_fail": "  Failed to fetch models. Check API connection.",
        "cfg_select_switch": "  Select number to switch (blank to cancel): ",
        "cfg_invalid": "  Invalid selection.",
        "cfg_thinking_status": "  OK thinking: {status}",
        "cfg_api_url_prompt": "  API URL [{current}]: ",
        "cfg_api_key_prompt": "  API Key [***]: ",
        "cfg_api_updated": "  OK API updated.",
        "cfg_reset_ok": "  OK config cleared.",
        "cfg_no_file": "  No config file.",
        "cfg_usage": "  Usage: config [show|setup|model|thinking|api|reset]",
        "cfg_thinking_on": "on",
        "cfg_thinking_off": "off",
    },
    "zh": {
        "banner": "aiCLI v{version} — AI 智能命令行 Agent",
        "banner_sub": "你说人话，它替你敲命令。\n",
        "llm_label": "LLM:   {model} [{mode}]",
        "api_label": "API:   {api}",
        "mode_label": "模式:   Agent 自主执行（低风险自动，高风险确认）",
        "config_hint": "config          查看配置 | config model 切换模型",
        "context_hint": "context <描述>  设置项目上下文",
        "help_hint": "help            全部命令",
        "not_configured": "未检测到 LLM 配置。\n",
        "setup_required": "aiCLI 需要 LLM 才能工作。配置后重新启动。",
        "connecting": "... 连接 {user}@{host}:{port}...",
        "connected": "[OK] 已连接 | {os} | {cores}核/{ram}GB/{disk}GB",
        "installed": "  已装: {items}",
        "connect_failed": "[X] 连接失败: {error}",
        "port_unreachable": "\n  端口 {port} 不可达，可能原因：",
        "cause_no_ssh": "    1. 目标机器未开启 SSH 服务",
        "cause_firewall": "    2. 防火墙阻止了端口 {port}",
        "cause_wrong_addr": "    3. IP 地址或端口错误",
        "install_windows": "\n  如果目标机器是 Windows，需先安装 OpenSSH Server：",
        "install_win_cmd1": "    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0",
        "install_win_cmd2": "    Start-Service sshd",
        "install_win_cmd3": "    Set-Service -Name sshd -StartupType Automatic",
        "install_linux": "\n  如果目标机器是 Linux：",
        "install_linux_cmd1": "    sudo apt install openssh-server   # Debian/Ubuntu",
        "install_linux_cmd2": "    sudo yum install openssh-server   # CentOS/RHEL",
        "install_linux_cmd3": "    sudo systemctl start sshd",
        "port_ok_auth": "\n  端口 {port} 可达但连接失败，可能是认证问题。检查用户名和密码。",
        "already_connected": "已有连接，先 disconnect\n",
        "not_connected": "未连接\n",
        "usage_connect": "用法: connect <user@host[:port]> [密码]\n",
        "usage_exec": "用法: exec <命令>\n",
        "usage_file_read": "用法: file_read <路径>\n",
        "usage_file_write": "用法: file_write <路径> <内容>\n",
        "usage_run": "用法: run <任务描述>\n",
        "disconnected": "[OK] {msg}\n",
        "context_set": "  [OK] 上下文已设置\n",
        "context_clear": "  [OK] 上下文已清除\n",
        "context_current": "  当前上下文: {ctx}\n",
        "local_connected": "[OK] 本机模式 | {os} | {cores}核/{ram}GB",
        "lang_select": "选择语言 / Select language:",
        "lang_en": "  [1] English",
        "lang_zh": "  [2] 中文（默认）",
        "lang_prompt": "选择 [2]: ",
        "lang_saved": "语言设置为中文。\n",
        "thinking": "  [thinking...]",
        "auto_exec": "  [auto] executing...",
        "confirm_exec": "  [Y]执行 / [n]跳过 / [q]退出 / <反馈>: ",
        "plan_confirm": "\n  确认执行此方案？[Y/调整意见]: ",
        "feedback": "  [feedback] adjusting...\n",
        "skipped": "  skipped\n",
        "aborted": "  [ABORT] task cancelled\n",
        "user_interrupt": "\n\n  ⏸ 用户中断（Ctrl+C）",
        "interrupt_choice": "  [r]重试 / [k]终止 / <反馈意见>: ",
        "byz": "bye",
        "unknown_cmd": "未知命令: {cmd}，输入 help 查看帮助\n",
        "not_connected_run": "未连接，先 local 或 connect\n",
        "task_header": "\n{sep}\n  TASK: {task}\n{sep}\n",
        "done_header": "\n{sep}",
        "done_footer": "{sep}",
        "done_summary": "[DONE] | {count} commands executed (compressed {comp}x)",
        "step_header": "\n{sep}",
        "step_num": "  Step {n}",
        "step_think": "  THINK: {think}",
        "step_goal": "  GOAL:  {goal}",
        "step_cmd": "  CMD:   {cmd}",
        "step_risk": "  RISK:  {risk} {icon}  [{label}]",
        "result_ok": "\n[OK] | {ms}ms",
        "result_fail": "\n[X] (exit {code}) | {ms}ms",
        "stderr_label": "[stderr] {stderr}",
        "waiting": "\r  [waiting... {sec}s]",
        "ctrl_c_hint": "  [i] Ctrl+C 不退出 aiCLI，输入 quit/exit 退出\n",
        "ctrl_c_exit": "\n  [!] 连续 3 次 Ctrl+C，退出",
        "sudo_prompt": "  [sudo] password: ",
        "compressed": "\n  [context compressed: {old} -> {new} msgs, {old_chars} -> {new_chars} chars]\n",
        "plan_title": "\n{sep}",
        "local_mode_label": "local",
        "help_text": """
aiCLI v{version} — AI 智能命令行 Agent

LLM 配置:
  config                              查看当前配置
  config setup                        重新配置（向导模式）
  config model [模型名]                切换模型
  config thinking [on|off]            切换思考模式
  config api                          修改 API 地址/密钥
  config reset                        清除配置

连接:
  local                               本机模式（在本机智能执行命令）
  connect <user@host[:port]> [密码]   连接远程主机
  disconnect                          断开
  sessions                            查看连接

系统:
  probe                               探测系统信息

操作:
  exec <命令>                         手动执行单条命令
  file_read <路径>                    读取远程文件
  file_write <路径> <内容>            写入远程文件

上下文:
  context <描述>                      设置项目上下文（Agent 会记住目标和背景）
  context                             查看当前上下文
  context clear                       清除上下文

AI 任务:
  run <任务描述>                      Agent 规划并执行任务
  <自然语言>                          连接状态下直接输入（等同于 run）

执行控制:
  [auto]           Agent 自动执行（低风险）
  [confirm] Y/回车  确认执行高风险操作
         n         跳过当前步骤
         q         终止整个任务
         <任意文字>  当作反馈传给 Agent 调整方案
  Ctrl+C           暂停当前任务，反馈后继续（不退出）
  quit/exit         退出 aiCLI
""",
        "cli_help": """aiCLI v{version} — AI 智能命令行 Agent

用法:
  aicli                            启动交互模式（首次运行自动配置向导）
  aicli --local                    本机模式（在本机智能执行命令）
  aicli config                     查看当前 LLM 配置
  aicli config setup               重新配置 LLM（向导）
  aicli config model [名称]         切换模型
  aicli config thinking [on|off]    切换思考模式
  aicli config api                 修改 API 地址/密钥
  aicli config reset               清除配置

选项:
  --host <host>       启动时自动连接
  --port <port>       SSH 端口 (默认22)
  --user <user>       用户名 (默认root)
  --password <pwd>    密码
  --local             本机模式
  --llm <url>         LLM API 地址
  --model <model>     LLM 模型名
  --lang <en|zh>      语言 (默认zh)

配置优先级: 命令行参数 > 环境变量 > 配置文件
配置文件: {config_path}""",
        "setup_wizard_title": "  aicli 首次运行 — LLM 配置向导",
        "setup_wizard_desc": "  aicli 需要连接大模型 API 来提供 AI 能力。\n  支持任何 OpenAI 兼容 API（LiteLLM / OpenAI / 智谱 / ...）",
        "setup_api_url": "  API 地址 [{default}]: ",
        "setup_api_key": "  API Key: ",
        "setup_fetching": "  正在获取可用模型...",
        "setup_connect_fail": "  连接失败: {err}",
        "setup_manual": "  输入模型名称手动配置（留空退出）: ",
        "setup_cancelled": "  配置取消。",
        "setup_manual_ok": "\n  OK 已配置模型: {model}",
        "setup_config_saved": "  配置保存到: {path}",
        "setup_found": "  找到 {count} 个模型:",
        "setup_select": "  选择模型编号 [1]: ",
        "setup_done": "\n  OK 配置完成！",
        "setup_done_api": "     API:     {api}",
        "setup_done_model": "     模型:     {model}",
        "setup_done_path": "     配置:     {path}",
        "cfg_not_configured": "  未配置。运行 aicli 进入首次配置向导。",
        "cfg_api": "  API:      {api}",
        "cfg_model": "  模型:     {model}",
        "cfg_key": "  Key:      {key}",
        "cfg_thinking": "  思考模式: {status}",
        "cfg_file": "  文件:     {path}",
        "cfg_model_switched": "  OK 模型已切换为: {model}",
        "cfg_no_api": "  未配置 API，先运行 aicli config setup",
        "cfg_fetch_fail": "  获取失败，请检查 API 连接",
        "cfg_select_switch": "  选择编号切换（留空取消）: ",
        "cfg_invalid": "  无效选择",
        "cfg_thinking_status": "  OK 思考模式: {status}",
        "cfg_api_url_prompt": "  API 地址 [{current}]: ",
        "cfg_api_key_prompt": "  API Key [***]: ",
        "cfg_api_updated": "  OK API 已更新",
        "cfg_reset_ok": "  OK 配置已清除",
        "cfg_no_file": "  无配置文件",
        "cfg_usage": "  用法: config [show|setup|model|thinking|api|reset]",
        "cfg_thinking_on": "开启",
        "cfg_thinking_off": "关闭",
    },
}


def get_lang() -> str:
    return _LANG


def set_lang(lang: str):
    global _LANG
    _LANG = lang if lang in _MESSAGES else "en"


def t(key: str, **kwargs) -> str:
    msgs = _MESSAGES.get(_LANG, _MESSAGES["en"])
    template = msgs.get(key, _MESSAGES["en"].get(key, key))
    if kwargs:
        return template.format(**kwargs)
    return template


def init_lang_from_config():
    global _LANG
    config_dir = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    lang_file = Path(config_dir) / "aicli" / "lang.json"
    if lang_file.exists():
        try:
            data = json.loads(lang_file.read_text(encoding="utf-8"))
            set_lang(data.get("lang", "en"))
        except Exception:
            pass


def save_lang(lang: str):
    config_dir = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    lang_dir = Path(config_dir) / "aicli"
    lang_dir.mkdir(parents=True, exist_ok=True)
    lang_file = lang_dir / "lang.json"
    lang_file.write_text(json.dumps({"lang": lang}), encoding="utf-8")
    set_lang(lang)


def first_run_lang_select() -> str:
    print()
    print(t("lang_select"))
    print(t("lang_en"))
    print(t("lang_zh"))
    choice = input(t("lang_prompt")).strip()
    lang = "zh" if choice == "2" else "en"
    save_lang(lang)
    print(t("lang_saved"))
    return lang
