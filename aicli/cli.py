import asyncio
import getpass
import socket
import sys

from . import __version__
from .config import is_configured, first_run_setup, config_command, get_llm_config, _CONFIG_PATH as config_file_path
from .llm import get_client, get_model, build_env_info
from .session import SessionManager
from .reactor import run_task
from .i18n import t, get_lang, set_lang, init_lang_from_config, save_lang, first_run_lang_select

CTRL_C_COUNT = 0


async def _cli_sudo_password_callback() -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: getpass.getpass(t("sudo_prompt")),
    )


def _safe_input(prompt: str) -> str:
    global CTRL_C_COUNT
    try:
        return input(prompt).strip()
    except KeyboardInterrupt:
        CTRL_C_COUNT += 1
        print("^C")
        if CTRL_C_COUNT >= 3:
            print(t("ctrl_c_exit"))
            raise SystemExit(0)
        print(t("ctrl_c_hint"))
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

    print(t("banner", version=__version__))
    print(t("banner_sub"))

    if not is_configured():
        print(t("not_configured"))
        ok = first_run_setup()
        if not ok:
            print(t("setup_required"))
            return
        print()

    llm_cfg = get_llm_config()
    thinking_status = "thinking" if llm_cfg.get("thinking") else "fast"

    try:
        model = get_model()
        client = get_client()
        client.models.list()
        print(t("llm_label", model=model, mode=thinking_status))
    except Exception as e:
        print(f"  LLM:   unavailable ({e})")
        print("         run 'config setup' to reconfigure")
    print(t("api_label", api=llm_cfg.get('base_url', '?')))
    print()
    print(t("mode_label"))
    print()
    print(t("config_hint"))
    print(t("context_hint"))
    print(t("help_hint"))
    print()

    if is_local:
        result = await mgr.create_local()
        session_id = result["session_id"]
        probe_data = result["probe"]
        print(t("local_connected", os=probe_data['os'], cores=probe_data['cpu_cores'], ram=probe_data['memory_gb']))
        if probe_data.get("installed"):
            items = ", ".join(f"{k}={v}" for k, v in probe_data["installed"].items() if v)
            if items:
                print(t("installed", items=items))
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
                print(t("context_current", ctx=context or "(not set)"))
            elif parts[1] == "clear":
                context = ""
                print(t("context_clear"))
            else:
                context = line.split(maxsplit=1)[1]
                print(t("context_set"))
        elif cmd == "connect":
            if session_id:
                print(t("already_connected"))
                continue
            rest = line.split(maxsplit=1)
            arg = rest[1] if len(rest) > 1 else ""
            result = await _handle_connect(mgr, arg)
            if result:
                session_id, probe_data = result
        elif cmd == "local":
            if session_id:
                print(t("already_connected"))
                continue
            result = await mgr.create_local()
            session_id = result["session_id"]
            probe_data = result["probe"]
            print(t("local_connected", os=probe_data['os'], cores=probe_data['cpu_cores'], ram=probe_data['memory_gb']))
            if probe_data.get("installed"):
                items = ", ".join(f"{k}={v}" for k, v in probe_data["installed"].items() if v)
                if items:
                    print(t("installed", items=items))
            print()
            _print_usage_after_connect(probe_data)
        elif cmd == "disconnect":
            if session_id:
                msg = await mgr.close(session_id)
                print(t("disconnected", msg=msg))
                session_id = None
                probe_data = None
            else:
                print(t("not_connected"))
        elif cmd == "probe":
            if not session_id:
                print(t("not_connected"))
                continue
            conn = mgr.get(session_id)
            p = await conn.probe()
            probe_data = mgr._probe_to_dict(p)
            _print_probe(probe_data)
        elif cmd == "sessions":
            for s in mgr.list_sessions():
                st = "[OK] connected" if s["connected"] else "[X] disconnected"
                print(f"  {s['session_id']} — {st}")
            print()
        elif cmd == "exec":
            if not session_id:
                print(t("not_connected"))
                continue
            rest = line.split(maxsplit=1)
            if len(rest) < 2:
                print(t("usage_exec"))
                continue
            conn = mgr.get(session_id)
            result = await conn.exec(rest[1])
            if result.exit_code == 0:
                print(t("result_ok", ms=result.duration_ms))
            else:
                print(t("result_fail", code=result.exit_code, ms=result.duration_ms))
            if result.stdout:
                print(result.stdout)
            if result.stderr and result.exit_code != 0:
                print(t("stderr_label", stderr=result.stderr))
            print()
        elif cmd == "file_read":
            if not session_id:
                print(t("not_connected"))
                continue
            rest = line.split(maxsplit=1)
            if len(rest) < 2:
                print(t("usage_file_read"))
                continue
            conn = mgr.get(session_id)
            try:
                content = await conn.file_read(rest[1])
                print(content)
            except Exception as e:
                print(f"[X] {e}\n")
        elif cmd == "file_write":
            if not session_id:
                print(t("not_connected"))
                continue
            rest = line.split(maxsplit=2)
            if len(rest) < 3:
                print(t("usage_file_write"))
                continue
            conn = mgr.get(session_id)
            try:
                await conn.file_write(rest[1], rest[2])
                print(f"[OK] written to {rest[1]}\n")
            except Exception as e:
                print(f"[X] {e}\n")
        elif cmd == "run":
            if not session_id:
                print(t("not_connected_run"))
                continue
            rest = line.split(maxsplit=1)
            if len(rest) < 2:
                print(t("usage_run"))
                continue
            conn = mgr.get(session_id)
            sep = "=" * 50
            print(t("task_header", sep=sep, task=rest[1]))
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
                print("\n  [⏸] Task paused\n")
        else:
            if session_id:
                conn = mgr.get(session_id)
                sep = "=" * 50
                print(t("task_header", sep=sep, task=line))
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
                    print("\n  [⏸] Task paused\n")
            else:
                print(t("unknown_cmd", cmd=cmd))

    if session_id:
        await mgr.close(session_id)
    print(t("byz"))


def _print_usage_after_connect(probe_data: dict | None):
    host = probe_data.get("hostname", "?") if probe_data else "?"
    sep = "─" * 50
    print(sep)
    print(f"  {host} ready — Agent mode")
    print(sep)
    print()
    print("  Type a task description, Agent plans and executes:")
    print("    check system info")
    print("    install Docker and deploy a web app")
    print("    check Nginx config and restart")
    print()
    print("  Commands:")
    print("    probe            Detect system info")
    print("    exec <cmd>       Execute a single command")
    print("    context <desc>   Set project context")
    print()
    print("  Execution control:")
    print("    [auto]           Low-risk ops execute automatically")
    print("    [confirm]        High-risk ops require Y")
    print("    Ctrl+C           Pause task, give feedback")
    print("    quit/exit        Exit aiCLI")
    print(sep)
    print()


def _print_help(connected: bool):
    print(t("help_text", version=__version__))


async def _handle_connect(mgr: SessionManager, arg: str):
    if not arg:
        print(t("usage_connect"))
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
    print(t("connecting", user=kwargs.get('username', 'root'), host=host, port=port))
    try:
        result = await mgr.create_ssh(host=host, **kwargs)
        sid = result["session_id"]
        probe = result["probe"]
        print(t("connected", os=probe['os'], cores=probe['cpu_cores'], ram=probe['memory_gb'], disk=probe['disk_total_gb']))
        if probe.get("installed"):
            items = ", ".join(f"{k}={v}" for k, v in probe["installed"].items() if v)
            if items:
                print(t("installed", items=items))
        print()
        return sid, probe
    except Exception as e:
        _print_connect_error(host, port, e)
        return None, None


def _print_connect_error(host: str, port: int, error: Exception):
    err_str = str(error)
    is_timeout = any(k in err_str.lower() for k in ("timeout", "timed out", "信号灯", "121"))
    is_refused = any(k in err_str.lower() for k in ("refused", "10061", "connection refused"))

    print(t("connect_failed", error=error))

    if is_timeout or is_refused:
        reachable = _check_port(host, port)
        if not reachable:
            print(t("port_unreachable", port=port))
            print(t("cause_no_ssh"))
            print(t("cause_firewall", port=port))
            print(t("cause_wrong_addr"))

            if port == 22:
                print(t("install_windows"))
                print(t("install_win_cmd1"))
                print(t("install_win_cmd2"))
                print(t("install_win_cmd3"))
                print()
                print(t("install_linux"))
                print(t("install_linux_cmd1"))
                print(t("install_linux_cmd2"))
                print(t("install_linux_cmd3"))
        else:
            print(t("port_ok_auth", port=port))
    print()


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
    print(f"\nSystem info:")
    print(f"  OS:    {d['os']} ({d['arch']})")
    print(f"  Host:  {d['hostname']} | IP: {d.get('ip', '?')}")
    print(f"  Kernel: {d.get('kernel', '?')}")
    print(f"  CPU:   {d['cpu_cores']} cores")
    print(f"  Memory: {d['memory_gb']}GB")
    print(f"  Disk:  {d['disk_used_gb']}GB / {d['disk_total_gb']}GB")
    print(f"  Pkg:   {d['package_manager']}")
    if d.get("installed"):
        items = ", ".join(f"{k}={v}" for k, v in d["installed"].items() if v)
        if items:
            print(f"  Installed: {items}")
    print()


def main():
    args = sys.argv[1:]

    init_lang_from_config()

    cli_lang = None

    if not args:
        config_dir_lang = config_file_path.replace("config.json", "lang.json")
        import json, os
        if not os.path.exists(config_dir_lang.replace("lang.json", "")):
            pass
        lang_path = os.path.join(os.path.dirname(config_file_path), "lang.json")
        if not os.path.exists(lang_path):
            first_run_lang_select()
        try:
            asyncio.run(interactive())
        except KeyboardInterrupt:
            print(f"\n{t('byz')}")
        return

    if args[0] == "config":
        config_command(args[1:])
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
        elif args[i] == "--lang" and i + 1 < len(args):
            cli_lang = args[i + 1]
            set_lang(cli_lang)
            save_lang(cli_lang)
            i += 2
        elif args[i] == "--local":
            kwargs["local"] = True
            i += 1
        elif args[i] in ("-h", "--help"):
            print(t("cli_help", version=__version__, config_path=config_file_path))
            sys.exit(0)
        else:
            i += 1

    try:
        asyncio.run(interactive(host=host, **kwargs))
    except KeyboardInterrupt:
        print(f"\n{t('byz')}")
