from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Awaitable


@dataclass
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    command: str


@dataclass
class ProbeResult:
    os_name: str
    os_version: str
    arch: str
    hostname: str
    kernel: str = ""
    cpu_cores: int = 0
    memory_total_gb: float = 0.0
    disk_total_gb: float = 0.0
    disk_used_gb: float = 0.0
    package_manager: str = ""
    shell: str = ""
    installed: dict = field(default_factory=dict)
    network: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)


SudoPasswordCallback = Callable[[], Awaitable[str]]


class Connector(ABC):
    def __init__(self):
        self._sudo_password_callback: SudoPasswordCallback | None = None

    def set_sudo_password_callback(self, callback: SudoPasswordCallback) -> None:
        self._sudo_password_callback = callback
    @abstractmethod
    async def connect(self, **kwargs) -> str:
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        pass

    @abstractmethod
    async def exec(self, command: str, timeout: int = 30, shell: str = "") -> ExecResult:
        pass

    @abstractmethod
    async def file_read(self, path: str) -> str:
        pass

    @abstractmethod
    async def file_write(self, path: str, content: str) -> None:
        pass

    @abstractmethod
    async def probe(self) -> ProbeResult:
        pass

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        pass
