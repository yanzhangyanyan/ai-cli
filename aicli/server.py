import asyncio
import json
import sys
import time

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .session import SessionManager
from .reactor import run_task

app = Server("aicli")
sessions = SessionManager()

_session_timestamps: dict[str, float] = {}
_SESSION_TTL = 3600


def _stderr_out(msg: str):
    print(msg, file=sys.stderr, flush=True)


def _no_op(prompt: str) -> str:
    return "y"


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="aicli_task",
            description="给 aicli 一个自然语言任务，aicli 自带 AI 自动规划并执行。"
                        "aicli 会连接远程机器、探测环境、规划步骤、逐步执行，全程白盒输出。"
                        "只需告诉它目标和连接信息。"
                        "支持 context（项目背景）和 session_memory（跨任务记忆）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "任务描述，如'安装 Docker 和 Docker Compose'"},
                    "host": {"type": "string", "description": "目标主机 IP 或域名"},
                    "port": {"type": "integer", "description": "SSH 端口，默认22", "default": 22},
                    "username": {"type": "string", "description": "用户名，默认root", "default": "root"},
                    "password": {"type": "string", "description": "密码"},
                    "client_keys": {"type": "array", "items": {"type": "string"}, "description": "SSH 私钥文件路径列表"},
                    "auto_confirm": {"type": "boolean", "description": "自动确认高风险操作（默认false）", "default": False},
                    "context": {"type": "string", "description": "项目上下文/背景信息，Agent 会参考", "default": ""},
                    "session_memory": {"type": "array", "items": {"type": "string"}, "description": "之前的任务摘要列表，用于跨任务记忆", "default": []},
                },
                "required": ["task", "host"],
            },
        ),
        Tool(
            name="aicli_local_task",
            description="在本机执行任务。aicli 会在本机（运行 aicli 的机器上）智能执行命令，无需 SSH。"
                        "适用于本机运维、软件安装、系统配置等场景。",
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "任务描述，如'检查本机Docker状态'"},
                    "auto_confirm": {"type": "boolean", "description": "自动确认高风险操作（默认false）", "default": False},
                    "context": {"type": "string", "description": "项目上下文/背景信息", "default": ""},
                },
                "required": ["task"],
            },
        ),
        Tool(
            name="aicli_connect",
            description="通过SSH连接远程主机，连接后自动探测系统信息。返回session_id和系统概况。",
            inputSchema={
                "type": "object",
                "properties": {
                    "host": {"type": "string", "description": "目标主机IP或域名"},
                    "port": {"type": "integer", "description": "SSH端口，默认22", "default": 22},
                    "username": {"type": "string", "description": "用户名，默认root", "default": "root"},
                    "password": {"type": "string", "description": "密码"},
                    "client_keys": {"type": "array", "items": {"type": "string"}, "description": "SSH 私钥文件路径列表"},
                },
                "required": ["host"],
            },
        ),
        Tool(
            name="aicli_exec",
            description="在远程主机上执行命令，实时返回输出。",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "会话ID"},
                    "command": {"type": "string", "description": "要执行的命令"},
                    "timeout": {"type": "integer", "description": "超时秒数，默认30", "default": 30},
                },
                "required": ["session_id", "command"],
            },
        ),
        Tool(
            name="aicli_file_read",
            description="读取远程主机上的文件内容",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "会话ID"},
                    "path": {"type": "string", "description": "文件绝对路径"},
                },
                "required": ["session_id", "path"],
            },
        ),
        Tool(
            name="aicli_file_write",
            description="写入内容到远程主机文件",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "会话ID"},
                    "path": {"type": "string", "description": "文件绝对路径"},
                    "content": {"type": "string", "description": "要写入的内容"},
                },
                "required": ["session_id", "path", "content"],
            },
        ),
        Tool(
            name="aicli_probe",
            description="探测远程主机系统信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "会话ID"},
                },
                "required": ["session_id"],
            },
        ),
        Tool(
            name="aicli_disconnect",
            description="断开远程连接",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "会话ID"},
                },
                "required": ["session_id"],
            },
        ),
        Tool(
            name="aicli_list_sessions",
            description="列出当前所有活跃的远程连接",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


def _cleanup_expired_sessions():
    now = time.monotonic()
    expired = [sid for sid, ts in _session_timestamps.items() if now - ts > _SESSION_TTL]
    for sid in expired:
        try:
            asyncio.ensure_future(sessions.close(sid))
        except Exception:
            pass
        _session_timestamps.pop(sid, None)
    if expired:
        _stderr_out(f"[aicli] cleaned up {len(expired)} expired sessions")


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "aicli_local_task":
            _cleanup_expired_sessions()

            task = arguments["task"]
            auto = arguments.get("auto_confirm", False)
            ctx = arguments.get("context", "")

            _stderr_out(f"\n--- aicli local task: {task[:80]}")

            result = await sessions.create_local()
            session_id = result["session_id"]
            probe_data = result["probe"]
            _session_timestamps[session_id] = time.monotonic()

            _stderr_out(f"    local | {probe_data['os']} | {probe_data['cpu_cores']}核/{probe_data['memory_gb']}GB")

            connector = sessions.get(session_id)

            summary = await run_task(
                task=task,
                connector=connector,
                probe_data=probe_data,
                auto_confirm=auto,
                context=ctx,
                session_memory=None,
                output=_stderr_out,
                input_callback=_no_op if auto else None,
            )

            await sessions.close(session_id)
            _session_timestamps.pop(session_id, None)

            return [TextContent(
                type="text",
                text=json.dumps({
                    "task": task,
                    "mode": "local",
                    "summary": summary,
                }, ensure_ascii=False, indent=2),
            )]

        elif name == "aicli_task":
            _cleanup_expired_sessions()

            task = arguments["task"]
            host = arguments["host"]
            auto = arguments.get("auto_confirm", False)
            ctx = arguments.get("context", "")
            mem = arguments.get("session_memory", [])

            _stderr_out(f"\n--- aicli task: {task[:80]}")
            _stderr_out(f"    connect {arguments.get('username', 'root')}@{host}...")

            result = await sessions.create_ssh(
                host=host,
                port=arguments.get("port", 22),
                username=arguments.get("username", "root"),
                password=arguments.get("password"),
                client_keys=arguments.get("client_keys"),
            )
            session_id = result["session_id"]
            probe_data = result["probe"]
            _session_timestamps[session_id] = time.monotonic()

            _stderr_out(f"    connected | {probe_data['os']} | {probe_data['cpu_cores']}核/{probe_data['memory_gb']}GB")

            connector = sessions.get(session_id)

            summary = await run_task(
                task=task,
                connector=connector,
                probe_data=probe_data,
                auto_confirm=auto,
                context=ctx,
                session_memory=mem if mem else None,
                output=_stderr_out,
                input_callback=_no_op if auto else None,
            )

            await sessions.close(session_id)
            _session_timestamps.pop(session_id, None)

            return [TextContent(
                type="text",
                text=json.dumps({
                    "task": task,
                    "host": host,
                    "summary": summary,
                }, ensure_ascii=False, indent=2),
            )]

        elif name == "aicli_connect":
            _cleanup_expired_sessions()

            result = await sessions.create_ssh(
                host=arguments["host"],
                port=arguments.get("port", 22),
                username=arguments.get("username", "root"),
                password=arguments.get("password"),
                client_keys=arguments.get("client_keys"),
            )
            sid = result["session_id"]
            _session_timestamps[sid] = time.monotonic()
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

        elif name == "aicli_exec":
            sid = arguments["session_id"]
            _session_timestamps[sid] = time.monotonic()
            conn = sessions.get(sid)
            result = await conn.exec(
                command=arguments["command"],
                timeout=arguments.get("timeout", 30),
            )
            output = {
                "command": result.command,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "duration_ms": result.duration_ms,
            }
            return [TextContent(type="text", text=json.dumps(output, ensure_ascii=False, indent=2))]

        elif name == "aicli_file_read":
            conn = sessions.get(arguments["session_id"])
            content = await conn.file_read(arguments["path"])
            return [TextContent(type="text", text=content)]

        elif name == "aicli_file_write":
            conn = sessions.get(arguments["session_id"])
            await conn.file_write(arguments["path"], arguments["content"])
            return [TextContent(type="text", text=f"written to {arguments['path']}")]

        elif name == "aicli_probe":
            conn = sessions.get(arguments["session_id"])
            probe = await conn.probe()
            return [TextContent(
                type="text",
                text=json.dumps(sessions._probe_to_dict(probe), ensure_ascii=False, indent=2),
            )]

        elif name == "aicli_disconnect":
            sid = arguments["session_id"]
            msg = await sessions.close(sid)
            _session_timestamps.pop(sid, None)
            return [TextContent(type="text", text=msg)]

        elif name == "aicli_list_sessions":
            result = sessions.list_sessions()
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

        else:
            return [TextContent(type="text", text=f"unknown tool: {name}")]

    except KeyError as e:
        return [TextContent(type="text", text=f"error: {e}")]
    except Exception as e:
        return [TextContent(type="text", text=f"error: {type(e).__name__}: {e}")]


async def _run():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def serve():
    asyncio.run(_run())
