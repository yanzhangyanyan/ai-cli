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
            description="Give aiCLI a natural language task, it autonomously plans and executes. "
                        "aiCLI connects to the remote machine, probes the environment, plans steps, "
                        "and executes step by step with full transparency. "
                        "Just provide the goal and connection info. "
                        "Supports context (project background) and session_memory (cross-task memory).",
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Task description, e.g. 'Install Docker and Docker Compose'"},
                    "host": {"type": "string", "description": "Target host IP or domain"},
                    "port": {"type": "integer", "description": "SSH port, default 22", "default": 22},
                    "username": {"type": "string", "description": "Username, default root", "default": "root"},
                    "password": {"type": "string", "description": "Password"},
                    "client_keys": {"type": "array", "items": {"type": "string"}, "description": "SSH private key file paths"},
                    "auto_confirm": {"type": "boolean", "description": "Auto-confirm high-risk operations (default false)", "default": False},
                    "context": {"type": "string", "description": "Project context/background info for the Agent", "default": ""},
                    "session_memory": {"type": "array", "items": {"type": "string"}, "description": "Previous task summary list for cross-task memory", "default": []},
                },
                "required": ["task", "host"],
            },
        ),
        Tool(
            name="aicli_local_task",
            description="Execute a task locally. aiCLI runs commands on the local machine intelligently, no SSH needed. "
                        "Suitable for local ops, software installation, system configuration, etc.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Task description, e.g. 'Check local Docker status'"},
                    "auto_confirm": {"type": "boolean", "description": "Auto-confirm high-risk operations (default false)", "default": False},
                    "context": {"type": "string", "description": "Project context/background info", "default": ""},
                },
                "required": ["task"],
            },
        ),
        Tool(
            name="aicli_connect",
            description="Connect to a remote host via SSH, automatically probe system info. Returns session_id and system overview.",
            inputSchema={
                "type": "object",
                "properties": {
                    "host": {"type": "string", "description": "Target host IP or domain"},
                    "port": {"type": "integer", "description": "SSH port, default 22", "default": 22},
                    "username": {"type": "string", "description": "Username, default root", "default": "root"},
                    "password": {"type": "string", "description": "Password"},
                    "client_keys": {"type": "array", "items": {"type": "string"}, "description": "SSH private key file paths"},
                },
                "required": ["host"],
            },
        ),
        Tool(
            name="aicli_exec",
            description="Execute a command on a remote host, returns output in real time.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "command": {"type": "string", "description": "Command to execute"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds, default 30", "default": 30},
                },
                "required": ["session_id", "command"],
            },
        ),
        Tool(
            name="aicli_file_read",
            description="Read file content from a remote host",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "path": {"type": "string", "description": "Absolute file path"},
                },
                "required": ["session_id", "path"],
            },
        ),
        Tool(
            name="aicli_file_write",
            description="Write content to a file on a remote host",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "path": {"type": "string", "description": "Absolute file path"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["session_id", "path", "content"],
            },
        ),
        Tool(
            name="aicli_probe",
            description="Probe remote host system information",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                },
                "required": ["session_id"],
            },
        ),
        Tool(
            name="aicli_disconnect",
            description="Disconnect from a remote host",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                },
                "required": ["session_id"],
            },
        ),
        Tool(
            name="aicli_list_sessions",
            description="List all active remote connections",
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

            _stderr_out(f"    local | {probe_data['os']} | {probe_data['cpu_cores']} cores / {probe_data['memory_gb']}GB")

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

            _stderr_out(f"    connected | {probe_data['os']} | {probe_data['cpu_cores']} cores / {probe_data['memory_gb']}GB")

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
