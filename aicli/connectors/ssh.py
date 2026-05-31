import asyncio
import re
import time

import asyncssh

from .base import Connector, ExecResult, ProbeResult


class SSHConnector(Connector):
    def __init__(self):
        super().__init__()
        self._conn: asyncssh.SSHClientConnection | None = None
        self._host = ""
        self._port = 22
        self._username = ""

    async def connect(
        self,
        host: str,
        port: int = 22,
        username: str = "root",
        password: str | None = None,
        client_keys: list[str] | None = None,
        known_hosts: str | None = None,
    ) -> str:
        self._host = host
        self._port = port
        self._username = username

        kwargs: dict = {
            "host": host,
            "port": port,
            "username": username,
        }
        if password:
            kwargs["password"] = password
        if client_keys:
            kwargs["client_keys"] = client_keys
        kwargs["known_hosts"] = known_hosts if known_hosts else None

        self._conn = await asyncssh.connect(**kwargs)
        return f"connected to {username}@{host}:{port}"

    async def disconnect(self) -> None:
        if self._conn:
            self._conn.close()
            await self._conn.wait_closed()
            self._conn = None

    async def exec(self, command: str, timeout: int = 60, shell: str = "") -> ExecResult:
        if not self._conn:
            raise RuntimeError("not connected")

        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                self._conn.run(command, check=False, encoding="utf-8", errors="replace"),
                timeout=timeout,
            )
            duration_ms = int((time.monotonic() - start) * 1000)

            if self._is_sudo_password_required(result) and self._username != "root":
                return await self._exec_sudo_interactive(command, timeout, start)

            return ExecResult(
                exit_code=result.exit_status,
                stdout=result.stdout,
                stderr=result.stderr,
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
        if not self._conn:
            raise RuntimeError("not connected")

        start = time.monotonic()
        proc = None
        stdout_chunks = []
        stderr_chunks = []
        sudo_password_injected = False

        try:
            proc = await self._conn.create_process(command, encoding=None)

            async def _read_stream(stream, chunks):
                async for data in stream:
                    text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
                    chunks.append(text)
                    if on_output:
                        on_output(text)

            async def _watch_sudo_prompt(proc_obj):
                nonlocal sudo_password_injected
                buf = ""
                async for data in proc_obj.stdout:
                    text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
                    buf += text
                    stdout_chunks.append(text)
                    if on_output:
                        on_output(text)
                    if not sudo_password_injected and "[sudo]" in buf.lower() and "password" in buf.lower():
                        if self._username != "root" and proc_obj.stdin is not None:
                            password = await self._prompt_sudo_password()
                            if password:
                                proc_obj.stdin.write(password + "\n")
                                proc_obj.stdin.write_eof()
                                sudo_password_injected = True
                            buf = ""

            read_stdout = asyncio.ensure_future(
                _watch_sudo_prompt(proc) if self._username != "root"
                else _read_stream(proc.stdout, stdout_chunks)
            )
            read_stderr = asyncio.ensure_future(_read_stream(proc.stderr, stderr_chunks))

            gather_task = asyncio.gather(read_stdout, read_stderr)
            tasks_to_watch = [gather_task]
            if cancel_event is not None:
                cancel_task = asyncio.ensure_future(cancel_event.wait())
                tasks_to_watch.append(cancel_task)

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
                stdout = "".join(stdout_chunks)
                stderr = "".join(stderr_chunks) + "\n[user cancelled]"
                return ExecResult(
                    exit_code=-2, stdout=stdout, stderr=stderr,
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
                stdout = "".join(stdout_chunks)
                stderr = "".join(stderr_chunks) + f"\n[timeout after {timeout}s]"
                return ExecResult(
                    exit_code=-1, stdout=stdout, stderr=stderr,
                    duration_ms=duration_ms, command=command,
                )

            await asyncio.wait_for(proc.wait(), timeout=30)
            duration_ms = int((time.monotonic() - start) * 1000)
            stdout = "".join(stdout_chunks)
            stderr = "".join(stderr_chunks)

            if not self.is_connected:
                stderr += "\n[WARNING: SSH connection lost during execution]"

            if sudo_password_injected:
                stdout = re.sub(r'\[sudo\].*password.*?:\s*', '', stdout, flags=re.IGNORECASE)

            return ExecResult(
                exit_code=proc.exit_status,
                stdout=stdout,
                stderr=stderr,
                duration_ms=duration_ms,
                command=command,
            )
        except (KeyboardInterrupt, asyncio.CancelledError):
            if proc:
                try:
                    proc.kill()
                except Exception:
                    pass
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except Exception:
                    pass
            duration_ms = int((time.monotonic() - start) * 1000)
            stdout = "".join(stdout_chunks)
            stderr = "".join(stderr_chunks) + "\n[user cancelled]"
            return ExecResult(
                exit_code=-2, stdout=stdout, stderr=stderr,
                duration_ms=duration_ms, command=command,
            )
        except asyncssh.DisconnectError:
            if proc:
                try:
                    proc.kill()
                except Exception:
                    pass
            duration_ms = int((time.monotonic() - start) * 1000)
            return ExecResult(
                exit_code=-1, stdout="".join(stdout_chunks), stderr="SSH disconnected",
                duration_ms=duration_ms, command=command,
            )

    async def _exec_sudo_interactive(
        self, command: str, timeout: int, start: float
    ) -> ExecResult:
        password = await self._prompt_sudo_password()
        if not password:
            return ExecResult(
                exit_code=-1, stdout="", stderr="sudo password cancelled by user",
                duration_ms=int((time.monotonic() - start) * 1000), command=command,
            )

        sudo_cmd = self._inject_sudo_s(command)
        for attempt in range(3):
            if attempt > 0:
                print("  [sudo] retry...")
                password = await self._prompt_sudo_password()
                if not password:
                    return ExecResult(
                        exit_code=-1, stdout="", stderr="sudo password cancelled",
                        duration_ms=int((time.monotonic() - start) * 1000), command=command,
                    )
            try:
                result = await asyncio.wait_for(
                    self._conn.run(sudo_cmd, check=False, input=password + "\n"),
                    timeout=timeout,
                )
                if result.exit_status == 0 or "incorrect password" not in result.stderr.lower():
                    break
            except asyncio.TimeoutError:
                duration_ms = int((time.monotonic() - start) * 1000)
                return ExecResult(
                    exit_code=-1, stdout="", stderr=f"command timed out after {timeout}s",
                    duration_ms=duration_ms, command=command,
                )
            except (OSError, ConnectionError, asyncssh.DisconnectError):
                duration_ms = int((time.monotonic() - start) * 1000)
                return ExecResult(
                    exit_code=-1, stdout="", stderr="SSH connection lost during sudo",
                    duration_ms=duration_ms, command=command,
                )

        duration_ms = int((time.monotonic() - start) * 1000)
        return ExecResult(
            exit_code=result.exit_status,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_ms=duration_ms,
            command=command,
        )

    @staticmethod
    def _is_sudo_password_required(result) -> bool:
        combined = (result.stderr + result.stdout).lower()
        return result.exit_status != 0 and "sudo" in combined and "password" in combined

    @staticmethod
    def _inject_sudo_s(command: str) -> str:
        result = re.sub(r'\bsudo\b', 'sudo -S', command)
        result = re.sub(r'\bsudo\s+-S\s+-n\b', 'sudo -S', result)
        return result

    async def _prompt_sudo_password(self) -> str | None:
        if self._sudo_password_callback:
            return await self._sudo_password_callback()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_prompt_password)

    @staticmethod
    def _sync_prompt_password() -> str | None:
        import getpass
        try:
            return getpass.getpass("  [sudo] password: ")
        except (EOFError, KeyboardInterrupt):
            return None

    async def file_read(self, path: str) -> str:
        result = await self.exec(f"cat '{path}'")
        if result.exit_code != 0:
            raise FileNotFoundError(f"cannot read {path}: {result.stderr}")
        return result.stdout

    async def file_write(self, path: str, content: str) -> None:
        cmd = f"cat > '{path}' << 'AICLI_EOF'\n{content}\nAICLI_EOF"
        result = await self.exec(cmd)
        if result.exit_code != 0:
            raise IOError(f"cannot write {path}: {result.stderr}")

    async def probe(self) -> ProbeResult:
        test = await self.exec("uname -s", timeout=5)
        is_linux = test.exit_code == 0 and "linux" in test.stdout.lower()
        is_mac = test.exit_code == 0 and "darwin" in test.stdout.lower()

        if is_linux or is_mac:
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
        else:
            commands = {
                "os_name": "echo Windows",
                "os_version": 'powershell -Command "[Environment]::OSVersion.Version.ToString()"',
                "arch": "echo %PROCESSOR_ARCHITECTURE%",
                "hostname": "hostname",
                "kernel": "echo N/A",
                "cpu_cores": 'powershell -Command "(Get-CimInstance Win32_Processor).NumberOfLogicalProcessors"',
                "mem_total": 'powershell -Command "[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)"',
                "disk_total": 'powershell -Command "[math]::Round((Get-PSDrive -Name C).Used / 1GB + (Get-PSDrive -Name C).Free / 1GB)"',
                "disk_used": 'powershell -Command "[math]::Round((Get-PSDrive -Name C).Used / 1GB)"',
                "pkg_manager": "echo winget",
                "shell_default": "echo powershell",
                "ip": 'powershell -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notmatch \'Loopback\' } | Select-Object -First 1).IPAddress"',
            }
            checks = [
                ("docker", "docker --version 2>nul"),
                ("python3", "python --version 2>nul"),
                ("node", "node --version 2>nul"),
                ("git", "git --version 2>nul"),
                ("curl", "curl --version 2>nul | findstr curl"),
            ]

        raw = {}
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
        return self._conn is not None and not self._conn.is_closed()
