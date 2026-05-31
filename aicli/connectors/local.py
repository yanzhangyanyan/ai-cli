import asyncio
import platform
import shutil
import subprocess
import time

from .base import Connector, ExecResult, ProbeResult


class LocalConnector(Connector):
    def __init__(self):
        super().__init__()
        self._connected = True

    async def connect(self, **kwargs) -> str:
        self._connected = True
        return f"connected locally ({platform.node()})"

    async def disconnect(self) -> None:
        self._connected = False

    async def exec(self, command: str, timeout: int = 60, shell: str = "") -> ExecResult:
        if not self._connected:
            raise RuntimeError("not connected")

        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                asyncio.create_subprocess_shell(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                ),
                timeout=timeout,
            )
            stdout_bytes, stderr_bytes = await result.communicate()
            duration_ms = int((time.monotonic() - start) * 1000)
            return ExecResult(
                exit_code=result.returncode or 0,
                stdout=stdout_bytes.decode("utf-8", errors="replace"),
                stderr=stderr_bytes.decode("utf-8", errors="replace"),
                duration_ms=duration_ms,
                command=command,
            )
        except asyncio.TimeoutError:
            duration_ms = int((time.monotonic() - start) * 1000)
            return ExecResult(
                exit_code=-1, stdout="", stderr=f"command timed out after {timeout}s",
                duration_ms=duration_ms, command=command,
            )

    async def exec_streaming(
        self,
        command: str,
        timeout: int = 300,
        on_output: "callable | None" = None,
        cancel_event: "asyncio.Event | None" = None,
    ) -> ExecResult:
        if not self._connected:
            raise RuntimeError("not connected")

        start = time.monotonic()
        stdout_chunks = []
        stderr_chunks = []

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdin=subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            async def _read_stream(stream, chunks):
                while True:
                    data = await stream.readline()
                    if not data:
                        break
                    text = data.decode("utf-8", errors="replace")
                    chunks.append(text)
                    if on_output:
                        on_output(text)

            read_stdout = asyncio.ensure_future(_read_stream(proc.stdout, stdout_chunks))
            read_stderr = asyncio.ensure_future(_read_stream(proc.stderr, stderr_chunks))

            tasks_to_watch = [asyncio.gather(read_stdout, read_stderr)]
            if cancel_event is not None:
                tasks_to_watch.append(asyncio.ensure_future(cancel_event.wait()))

            done, pending = await asyncio.wait(
                tasks_to_watch, timeout=timeout, return_when=asyncio.FIRST_COMPLETED,
            )

            for p in pending:
                p.cancel()
                try:
                    await p
                except (asyncio.CancelledError, Exception):
                    pass

            if cancel_event is not None and cancel_event.is_set():
                try:
                    proc.kill()
                except Exception:
                    pass
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except (asyncio.TimeoutError, Exception):
                    pass
                duration_ms = int((time.monotonic() - start) * 1000)
                return ExecResult(
                    exit_code=-2, stdout="".join(stdout_chunks),
                    stderr="".join(stderr_chunks) + "\n[user cancelled]",
                    duration_ms=duration_ms, command=command,
                )

            if not done:
                try:
                    proc.kill()
                except Exception:
                    pass
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except (asyncio.TimeoutError, Exception):
                    pass
                duration_ms = int((time.monotonic() - start) * 1000)
                return ExecResult(
                    exit_code=-1, stdout="".join(stdout_chunks),
                    stderr="".join(stderr_chunks) + f"\n[timeout after {timeout}s]",
                    duration_ms=duration_ms, command=command,
                )

            await asyncio.wait_for(proc.wait(), timeout=30)
            duration_ms = int((time.monotonic() - start) * 1000)
            return ExecResult(
                exit_code=proc.returncode or 0,
                stdout="".join(stdout_chunks),
                stderr="".join(stderr_chunks),
                duration_ms=duration_ms,
                command=command,
            )
        except (KeyboardInterrupt, asyncio.CancelledError):
            try:
                proc.kill()
            except Exception:
                pass
            duration_ms = int((time.monotonic() - start) * 1000)
            return ExecResult(
                exit_code=-2, stdout="".join(stdout_chunks),
                stderr="".join(stderr_chunks) + "\n[user cancelled]",
                duration_ms=duration_ms, command=command,
            )

    async def file_read(self, path: str) -> str:
        result = await self.exec(
            f'type "{path}"' if platform.system() == "Windows" else f"cat '{path}'"
        )
        if result.exit_code != 0:
            raise FileNotFoundError(f"cannot read {path}: {result.stderr}")
        return result.stdout

    async def file_write(self, path: str, content: str) -> None:
        is_win = platform.system() == "Windows"
        if is_win:
            escaped = content.replace("'", "''")
            cmd = f"Set-Content -Path '{path}' -Value '{escaped}' -Encoding UTF8"
        else:
            escaped = content.replace("'", "'\\''")
            cmd = f"cat > '{path}' << 'AICLI_EOF'\n{content}\nAICLI_EOF"
        result = await self.exec(cmd)
        if result.exit_code != 0:
            raise IOError(f"cannot write {path}: {result.stderr}")

    async def probe(self) -> ProbeResult:
        is_win = platform.system() == "Windows"
        raw = {}

        if is_win:
            commands = {
                "os_name": "echo Windows",
                "os_version": (
                    'powershell -Command "[Environment]::OSVersion.Version.ToString()"'
                ),
                "arch": "echo %PROCESSOR_ARCHITECTURE%",
                "hostname": "hostname",
                "kernel": "echo N/A",
                "cpu_cores": (
                    'powershell -Command "(Get-CimInstance Win32_Processor).NumberOfLogicalProcessors"'
                ),
                "mem_total": (
                    'powershell -Command "[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)"'
                ),
                "disk_total": (
                    'powershell -Command "[math]::Round((Get-PSDrive -Name C).Used / 1GB + (Get-PSDrive -Name C).Free / 1GB)"'
                ),
                "disk_used": (
                    'powershell -Command "[math]::Round((Get-PSDrive -Name C).Used / 1GB)"'
                ),
                "pkg_manager": "echo winget",
                "shell_default": "echo powershell",
                "ip": (
                    'powershell -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notmatch \'Loopback\' } | Select-Object -First 1).IPAddress"'
                ),
            }
            checks = [
                ("docker", "docker --version 2>nul"),
                ("python3", "python --version 2>nul"),
                ("node", "node --version 2>nul"),
                ("git", "git --version 2>nul"),
                ("curl", "curl --version 2>nul | findstr curl"),
            ]
        else:
            commands = {
                "os_name": "cat /etc/os-release 2>/dev/null | grep ^ID= | cut -d= -f2 | tr -d '\"'",
                "os_version": "cat /etc/os-release 2>/dev/null | grep ^VERSION_ID= | cut -d= -f2 | tr -d '\"'",
                "arch": "uname -m",
                "hostname": "hostname",
                "kernel": "uname -r",
                "cpu_cores": "nproc",
                "mem_total": "free -g 2>/dev/null | awk 'NR==2{print $2}' || sysctl -n hw.memsize 2>/dev/null | awk '{print int($1/1024/1024/1024)}'",
                "disk_total": "df -BG / 2>/dev/null | awk 'NR==2{print $2}' | tr -d G",
                "disk_used": "df -BG / 2>/dev/null | awk 'NR==2{print $3}' | tr -d G",
                "pkg_manager": "(command -v apt-get >/dev/null 2>&1 && echo apt-get) || (command -v apt >/dev/null 2>&1 && echo apt) || (command -v dnf >/dev/null 2>&1 && echo dnf) || (command -v yum >/dev/null 2>&1 && echo yum) || (command -v pacman >/dev/null 2>&1 && echo pacman) || (command -v brew >/dev/null 2>&1 && echo brew) || echo unknown",
                "shell_default": "echo $SHELL",
                "ip": "hostname -I 2>/dev/null | awk '{print $1}' || ifconfig 2>/dev/null | grep 'inet ' | grep -v 127.0.0.1 | awk '{print $2}' | head -1",
            }
            checks = [
                ("docker", "docker --version 2>/dev/null | awk '{print $3}' | tr -d ','"),
                ("python3", "python3 --version 2>/dev/null | awk '{print $2}'"),
                ("node", "node --version 2>/dev/null"),
                ("git", "git --version 2>/dev/null | awk '{print $3}'"),
                ("curl", "curl --version 2>/dev/null | head -1 | awk '{print $2}'"),
            ]

        for key, cmd in {**commands, **{k: v for k, v in checks}}.items():
            r = await self.exec(cmd, timeout=10)
            raw[key] = r.stdout.strip() if r.exit_code == 0 else ""

        return ProbeResult(
            os_name=raw.get("os_name", "unknown"),
            os_version=raw.get("os_version", "unknown"),
            arch=raw.get("arch", "unknown"),
            hostname=raw.get("hostname", "unknown"),
            kernel=raw.get("kernel", ""),
            cpu_cores=int(raw.get("cpu_cores", "0") or "0"),
            memory_total_gb=float(raw.get("mem_total", "0") or "0"),
            disk_total_gb=float(raw.get("disk_total", "0") or "0"),
            disk_used_gb=float(raw.get("disk_used", "0") or "0"),
            package_manager=raw.get("pkg_manager", "unknown"),
            shell=raw.get("shell_default", ""),
            installed={k: raw.get(k, "") for k, _ in checks if raw.get(k)},
            network={"ip": raw.get("ip", "")},
            raw=raw,
        )

    @property
    def is_connected(self) -> bool:
        return self._connected
