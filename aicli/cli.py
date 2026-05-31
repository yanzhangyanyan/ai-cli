import asyncio
import getpass
import os
import re
import socket
import sys

from .config import is_configured, first_run_setup, config_command, get_llm_config, _CONFIG_PATH as config_file_path
from .llm import get_client, get_model, build_env_info
from .session import SessionManager
from .reactor import run_task

CTRL_C_COUNT = 0


async def _cli_sudo_password_callback() -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: getpass.getpass("  [sudo] password: "),
    )


def _safe_input(prompt: str) -> str:
    global CTRL_C_COUNT
    try:
        return input(prompt).strip()
    except KeyboardInterrupt:
        CTRL_C_COUNT += 1
        print("^C")
        if CTRL_C_COUNT >= 3:
            print("\n  [!] 连续 3 次 Ctrl+C，退出")
            raise SystemExit(0)
        print("  [i] Ctrl+C 不退出 aicli，输入 quit/exit 退出\n")
        return ""
    except EOFError:
        raise SystemExit(0)


async def interactive(host: str | None = None, **connect_kwargs):
    global CTRL_C_COUNT

    mgr = SessionManager()
    mgr.set_sudo_password_callback(_cli_sudo_password_callback)
    session_id = None
    probe_data = None
    context = ""
    task_history: list[str] = []
    is_local = connect_kwargs.pop("local", False)

    print("aicli v0.6.0 — AI-Powered Command Line Agent (Agent)")
    print("AI 智能远程运维 Agent\n")

    if not is_configured():
        print("未检测到 LLM 配置。\n")
        ok = first_run_setup()
        if not ok:
            print("aicli 需要 LLM 才能工作。配置后重新启动。")
            return
        print()

    llm_cfg = get_llm_config()
    thinking_status = "思考" if llm_cfg.get("thinking") else "快速"

    try:
        model = get_model()
        client = get_client()
        client.models.list()
        print(f"  LLM:   {model} [{thinking_status}模式]")
    except Exception as e:
        print(f"  LLM:   不可用 ({e})")
        print("         运行 'config setup' 重新配置")
    print(f"  API:   {llm_cfg.get('base_url', '?')}")
    print()
    print("  模式:   Agent 自主执行（低风险自动，高风险确认）")
    print()
    print("  config          查看配置 | config model 切换模型")
    print("  context <描述>  设置项目上下文")
    print("  help            全部命令")
    print()

    if is_local:
        result = await mgr.create_local()
        session_id = result["session_id"]
        probe_data = result["probe"]
        print(f"[OK] 本机模式 | {probe_data['os']} | {probe_data['cpu_cores']}核/{probe_data['memory_gb']}GB")
        if probe_data.get("installed"):
            items = ", ".join(f"{k}={v}" for k, v in probe_data["installed"].items() if v)
            if items:
                print(f"  已装: {items}")
        print()
        _print_usage_after_connect(probe_data)

    if host:
        session_id, probe_data = await _do_connect(mgr, host, connect_kwargs)
        if session_id:
            _print_usage_after_connect(probe_data)

    while True:
        CTRL_C_COUNT = 0
        hostname = probe_data.get("hostname", "") if probe_data else ""
        prompt = f"aicli ({hostname})> " if hostname else "aicli> "
        line = _safe_input(prompt)

        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()

        if cmd in ("quit", "exit"):
            break
        elif cmd == "help":
            _print_help(session_id is not None)
        elif cmd == "config":
            config_command(parts[1:])
        elif cmd == "context":
            if len(parts) < 2:
                print(f"  当前上下文: {context or '(未设置)'}\n")
            elif parts[1] == "clear":
                context = ""
                print("  [OK] 上下文已清除\n")
            else:
                context = line.split(maxsplit=1)[1]
                print(f"  [OK] 上下文已设置: {context[:60]}...\n" if len(context) > 60 else f"  [OK] 上下文已设置\n")
        elif cmd == "connect":
            if session_id:
                print("已有连接，先 disconnect\n")
                continue
            rest = line.split(maxsplit=1)
            arg = rest[1] if len(rest) > 1 else ""
            result = await _handle_connect(mgr, arg)
            if result:
                session_id, probe_data = result
        elif cmd == "local":
            if session_id:
                print("已有连接，先 disconnect\n")
                continue
            result = await mgr.create_local()
            session_id = result["session_id"]
            probe_data = result["probe"]
            print(f"[OK] 本机模式 | {probe_data['os']} | {probe_data['cpu_cores']}核/{probe_data['memory_gb']}GB")
            if probe_data.get("installed"):
                items = ", ".join(f"{k}={v}" for k, v in probe_data["installed"].items() if v)
                if items:
                    print(f"  已装: {items}")
            print()
            _print_usage_after_connect(probe_data)
        elif cmd == "disconnect":
            if session_id:
                msg = await mgr.close(session_id)
                print(f"[OK] {msg}\n")
                session_id = None
                probe_data = None
            else:
                print("未连接\n")
        elif cmd == "probe":
            if not session_id:
                print("未连接\n")
                continue
            conn = mgr.get(session_id)
            p = await conn.probe()
            probe_data = mgr._probe_to_dict(p)
            _print_probe(probe_data)
        elif cmd == "sessions":
            for s in mgr.list_sessions():
                st = "[OK] 已连接" if s["connected"] else "[X] 断开"
                print(f"  {s['session_id']} — {st}")
            print()
        elif cmd == "exec":
            if not session_id:
                print("未连接\n")
                continue
            rest = line.split(maxsplit=1)
            if len(rest) < 2:
                print("用法: exec <command>\n")
                continue
            conn = mgr.get(session_id)
            result = await conn.exec(rest[1])
            status = "[OK]" if result.exit_code == 0 else f"[X] (exit {result.exit_code})"
            print(f"\n{status} | {result.duration_ms}ms")
            if result.stdout:
                print(result.stdout)
            if result.stderr and result.exit_code != 0:
                print(f"[stderr] {result.stderr}")
            print()
        elif cmd == "file_read":
            if not session_id:
                print("未连接\n")
                continue
            rest = line.split(maxsplit=1)
            if len(rest) < 2:
                print("用法: file_read <path>\n")
                continue
            conn = mgr.get(session_id)
            try:
                content = await conn.file_read(rest[1])
                print(content)
            except Exception as e:
                print(f"[X] {e}\n")
        elif cmd == "file_write":
            if not session_id:
                print("未连接\n")
                continue
            rest = line.split(maxsplit=2)
            if len(rest) < 3:
                print("用法: file_write <path> <content>\n")
                continue
            conn = mgr.get(session_id)
            try:
                await conn.file_write(rest[1], rest[2])
                print(f"[OK] 已写入 {rest[1]}\n")
            except Exception as e:
                print(f"[X] {e}\n")
        elif cmd == "run":
            if not session_id:
                print("未连接，先 connect\n")
                continue
            rest = line.split(maxsplit=1)
            if len(rest) < 2:
                print("用法: run <任务描述>\n")
                continue
            conn = mgr.get(session_id)
            print(f"\n{'=' * 50}")
            print(f"  TASK: {rest[1]}")
            print(f"{'=' * 50}\n")
            try:
                result = await run_task(
                    task=rest[1],
                    connector=conn,
                    probe_data=probe_data or {},
                    auto_confirm=False,
                    context=context,
                    session_memory=task_history,
                )
                if result:
                    task_history.append(f"「{rest[1][:40]}」→ {result}")
            except KeyboardInterrupt:
                print("\n  [⏸] 任务已暂停\n")
        else:
            if session_id:
                conn = mgr.get(session_id)
                print(f"\n{'=' * 50}")
                print(f"  TASK: {line}")
                print(f"{'=' * 50}\n")
                try:
                    result = await run_task(
                        task=line,
                        connector=conn,
                        probe_data=probe_data or {},
                        auto_confirm=False,
                        context=context,
                        session_memory=task_history,
                    )
                    if result:
                        task_history.append(f"「{line[:40]}」→ {result}")
                except KeyboardInterrupt:
                    print("\n  [⏸] 任务已暂停\n")
            else:
                print(f"未知命令: {cmd}，输入 help 查看帮助\n")

    if session_id:
        await mgr.close(session_id)
    print("bye")


def _print_usage_after_connect(probe_data: dict | None):
    host = probe_data.get("hostname", "?") if probe_data else "?"
    print(f"{'─' * 50}")
    print(f"  {host} 已就绪 — Agent 模式")
    print(f"{'─' * 50}")
    print()
    print("  直接输入任务描述，Agent 自动规划并执行:")
    print("    查看系统信息")
    print("    安装 Docker 并部署 RAGFlow")
    print("    检查 Nginx 配置并重启")
    print()
    print("  命令:")
    print("    probe            探测系统")
    print("    exec <命令>      手动执行单条命令")
    print("    context <描述>   设置项目上下文")
    print()
    print("  执行控制:")
    print("    [auto]           低风险操作自动执行")
    print("    [需确认]         高风险操作需 Y 确认")
    print("    Ctrl+C           暂停当前任务，可给反馈")
    print("    quit/exit        退出 aicli")
    print(f"{'─' * 50}")
    print()


def _print_help(connected: bool):
    print(f"""
aicli v0.5.0 — AI-Powered Command Line Agent (Agent)

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

执行中控制:
  [auto]           Agent 自动执行（低风险）
  [需确认] Y/回车   确认执行高风险操作
         n         跳过当前步骤
         <任意文字>  当作反馈传给 Agent 调整方案
  Ctrl+C           暂停当前任务，可输入反馈后继续
  quit/exit         退出 aicli（Ctrl+C 不退出，只暂停）
""")


async def _handle_connect(mgr: SessionManager, arg: str):
    if not arg:
        print("用法: connect <user@host[:port]> [password]\n")
        return None

    password = None
    parts = arg.split()
    target = parts[0]
    if len(parts) > 1:
        password = parts[1]

    username = "root"
    port = 22
    if "@" in target:
        username, target = target.split("@", 1)
    if ":" in target:
        target, port_str = target.rsplit(":", 1)
        port = int(port_str)

    return await _do_connect(mgr, target, {
        "port": port,
        "username": username,
        "password": password,
    })


async def _do_connect(mgr: SessionManager, host: str, kwargs: dict):
    port = kwargs.get("port", 22)
    print(f"... 连接 {kwargs.get('username', 'root')}@{host}:{port}...")
    try:
        result = await mgr.create_ssh(host=host, **kwargs)
        sid = result["session_id"]
        probe = result["probe"]
        print(f"[OK] 已连接 | {probe['os']} | {probe['cpu_cores']}核/{probe['memory_gb']}GB/{probe['disk_total_gb']}GB")
        if probe.get("installed"):
            items = ", ".join(f"{k}={v}" for k, v in probe["installed"].items() if v)
            if items:
                print(f"  已装: {items}")
        print()
        return sid, probe
    except Exception as e:
        _print_connect_error(host, port, e)
        return None, None


def _print_connect_error(host: str, port: int, error: Exception):
    err_str = str(error)
    is_timeout = any(k in err_str.lower() for k in ("timeout", "timed out", "信号灯", "121"))
    is_refused = any(k in err_str.lower() for k in ("refused", "10061", "connection refused"))

    print(f"[X] 连接失败: {error}")

    if is_timeout or is_refused:
        reachable = _check_port(host, port)
        if not reachable:
            print(f"\n  端口 {port} 不可达，可能原因：")
            print(f"    1. 目标机器未开启 SSH 服务")
            print(f"    2. 防火墙阻止了端口 {port}")
            print(f"    3. IP 地址或端口错误")

            if port == 22:
                print(f"\n  如果目标机器是 Windows，需先安装 OpenSSH Server：")
                print(f"    # 在目标机器上以管理员身份运行 PowerShell：")
                print(f"    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0")
                print(f"    Start-Service sshd")
                print(f"    Set-Service -Name sshd -StartupType Automatic")
                print()
                print(f"  如果目标机器是 Linux：")
                print(f"    sudo apt install openssh-server   # Debian/Ubuntu")
                print(f"    sudo yum install openssh-server   # CentOS/RHEL")
                print(f"    sudo systemctl start sshd")
        else:
            print(f"\n  端口 {port} 可达但连接失败，可能是认证问题。")
            print(f"    检查用户名和密码是否正确。")
    print()


def _update_command(extra_args: list[str]):
    import json as _json

    GITHUB_API = "https://api.github.com/repos/yanzhangyanyan/aicli/releases/latest"
    CURRENT = __import__("aicli").__version__

    print("aiCLI update\n")

    try:
        import urllib.request
        req = urllib.request.Request(GITHUB_API, headers={"User-Agent": "aicli"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = _json.loads(resp.read().decode("utf-8"))

        latest = data.get("tag_name", "").lstrip("v")
        if not latest:
            print("  No release found on GitHub.")
            return

        print(f"  Current: v{CURRENT}")
        print(f"  Latest:  v{latest}")
        print()

        if latest == CURRENT:
            print("  Already up to date.")
            return

        body = data.get("body", "")
        if body:
            print("  What's new:")
            for line in body.split("\n")[:10]:
                print(f"    {line}")
            print()

        assets = data.get("assets", [])
        tarball = data.get("tarball_url", "")
        zipball = data.get("zipball_url", "")

        print("  Update with:")
        print()
        print("    # From source")
        print(f"    git pull")
        print(f"    uv sync")
        print()
        print("    # Or reinstall")
        print(f"    pip install --upgrade aicli")
        print(f"    uv tool install git+https://github.com/yanzhangyanyan/aicli.git")

    except Exception as e:
        print(f"  Failed to check updates: {e}")
        print()
        print("  Manual update:")
        print("    git pull && uv sync")
        print("    pip install --upgrade aicli")


def _check_port(host: str, port: int, timeout: float = 5.0) -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except (socket.error, OSError):
        return False


def _print_probe(d: dict):
    print(f"\n系统信息:")
    print(f"  OS:    {d['os']} ({d['arch']})")
    print(f"  主机:  {d['hostname']} | IP: {d.get('ip', '?')}")
    print(f"  内核:  {d.get('kernel', '?')}")
    print(f"  CPU:   {d['cpu_cores']}核")
    print(f"  内存:  {d['memory_gb']}GB")
    print(f"  磁盘:  {d['disk_used_gb']}GB / {d['disk_total_gb']}GB")
    print(f"  包管:  {d['package_manager']}")
    if d.get("installed"):
        items = ", ".join(f"{k}={v}" for k, v in d["installed"].items() if v)
        if items:
            print(f"  已装:  {items}")
    print()


def main():
    args = sys.argv[1:]

    if not args:
        try:
            asyncio.run(interactive())
        except KeyboardInterrupt:
            print("\nbye")
        return

    if args[0] == "config":
        config_command(args[1:])
        return

    if args[0] == "update":
        _update_command(args[1:])
        return

    host = None
    kwargs = {}

    i = 0
    while i < len(args):
        if args[i] == "--host" and i + 1 < len(args):
            host = args[i + 1]
            i += 2
        elif args[i] == "--port" and i + 1 < len(args):
            kwargs["port"] = int(args[i + 1])
            i += 2
        elif args[i] == "--user" and i + 1 < len(args):
            kwargs["username"] = args[i + 1]
            i += 2
        elif args[i] == "--password" and i + 1 < len(args):
            kwargs["password"] = args[i + 1]
            i += 2
        elif args[i] == "--llm" and i + 1 < len(args):
            import os
            os.environ["AICLI_LLM_BASE_URL"] = args[i + 1]
            i += 2
        elif args[i] == "--model" and i + 1 < len(args):
            import os
            os.environ["AICLI_LLM_MODEL"] = args[i + 1]
            i += 2
        elif args[i] == "--local":
            kwargs["local"] = True
            i += 1
        elif args[i] in ("-h", "--help"):
            print("aicli v0.5.0 — AI-Powered Command Line Agent (Agent)\n")
            print("用法:")
            print("  aicli                            启动交互模式（首次运行自动配置向导）")
            print("  aicli --local                    本机模式（在本机智能执行命令）")
            print("  aicli config                     查看当前 LLM 配置")
            print("  aicli config setup               重新配置 LLM（向导）")
            print("  aicli config model [名称]         切换模型")
            print("  aicli config thinking [on|off]    切换思考模式")
            print("  aicli config api                 修改 API 地址/密钥")
            print("  aicli config reset               清除配置")
            print()
            print("启动选项:")
            print("  --host <host>       启动时自动连接")
            print("  --port <port>       SSH 端口 (默认22)")
            print("  --user <user>       用户名 (默认root)")
            print("  --password <pwd>    密码")
            print("  --llm <url>         LLM API 地址")
            print("  --model <model>     LLM 模型名")
            print()
            print("配置优先级: 命令行参数 > 环境变量 > 配置文件")
            print(f"配置文件: {config_file_path}")
            sys.exit(0)
        else:
            i += 1

    try:
        asyncio.run(interactive(host=host, **kwargs))
    except KeyboardInterrupt:
        print("\nbye")
