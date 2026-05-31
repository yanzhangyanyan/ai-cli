import uuid
from typing import Callable, Awaitable

from .connectors.base import Connector, ProbeResult, SudoPasswordCallback
from .connectors.ssh import SSHConnector
from .connectors.local import LocalConnector


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, Connector] = {}
        self._sudo_password_callback: SudoPasswordCallback | None = None

    def set_sudo_password_callback(self, callback: SudoPasswordCallback) -> None:
        self._sudo_password_callback = callback

    async def create_local(self) -> dict:
        connector = LocalConnector()
        msg = await connector.connect()
        session_id = f"local-{uuid.uuid4().hex[:8]}"
        self._sessions[session_id] = connector
        if self._sudo_password_callback:
            connector.set_sudo_password_callback(self._sudo_password_callback)
        probe = await connector.probe()
        return {
            "session_id": session_id,
            "message": msg,
            "probe": self._probe_to_dict(probe),
        }

    async def create_ssh(
        self,
        host: str,
        port: int = 22,
        username: str = "root",
        password: str | None = None,
        client_keys: list[str] | None = None,
    ) -> dict:
        connector = SSHConnector()
        msg = await connector.connect(
            host=host,
            port=port,
            username=username,
            password=password,
            client_keys=client_keys,
        )
        session_id = f"ssh-{uuid.uuid4().hex[:8]}"
        self._sessions[session_id] = connector
        if self._sudo_password_callback:
            connector.set_sudo_password_callback(self._sudo_password_callback)
        probe = await connector.probe()
        return {
            "session_id": session_id,
            "message": msg,
            "probe": self._probe_to_dict(probe),
        }

    def get(self, session_id: str) -> Connector:
        if session_id not in self._sessions:
            raise KeyError(f"session not found: {session_id}")
        return self._sessions[session_id]

    async def close(self, session_id: str) -> str:
        connector = self._sessions.pop(session_id, None)
        if not connector:
            return f"session {session_id} not found"
        await connector.disconnect()
        return f"session {session_id} closed"

    def list_sessions(self) -> list[dict]:
        result = []
        for sid, conn in self._sessions.items():
            result.append({
                "session_id": sid,
                "connected": conn.is_connected,
            })
        return result

    async def close_all(self):
        for sid in list(self._sessions):
            await self.close(sid)

    @staticmethod
    def _probe_to_dict(p: ProbeResult) -> dict:
        return {
            "os": f"{p.os_name} {p.os_version}",
            "arch": p.arch,
            "hostname": p.hostname,
            "kernel": p.kernel,
            "cpu_cores": p.cpu_cores,
            "memory_gb": p.memory_total_gb,
            "disk_total_gb": p.disk_total_gb,
            "disk_used_gb": p.disk_used_gb,
            "package_manager": p.package_manager,
            "shell": p.shell,
            "installed": p.installed,
            "ip": p.network.get("ip", ""),
        }
