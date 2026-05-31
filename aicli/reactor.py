import asyncio
import re
import sys
import time as _time

from .connectors.base import Connector, ExecResult
from .llm import SYSTEM_PROMPT, build_env_info, build_context_section, chat
from .session import SessionManager

_MAX_STEPS = 200
_MAX_OBSERVE_CHARS = 8000
_COMPRESS_THRESHOLD = 16
_COMPRESS_KEEP_RECENT = 6

_FORCED_CONFIRM_PATTERNS = [
    r'\brm\s+-rf\b', r'\brm\s+/',
    r'\bmkfs\b', r'\bdd\s+if=', r'\bformat\b',
    r'\breboot\b', r'\bshutdown\b', r'\bpoweroff\b',
]

_FORCED_CONFIRM_PATHS = [
    '/etc/', '/boot/', '/usr/lib', '/usr/bin/',
    '/lib/systemd/', '/etc/ssh/', '/etc/sudoers',
]


def _truncate(text: str, limit: int = _MAX_OBSERVE_CHARS) -> str:
    if len(text) <= limit:
        return text
    head = limit // 2 - 25
    tail = limit // 2 - 25
    return text[:head] + f"\n... [截断，共 {len(text)} 字符，保留头尾] ...\n" + text[-tail:]


def _count_messages_chars(messages: list[dict]) -> int:
    return sum(len(m.get("content", "")) for m in messages)


def _parse_step(text: str) -> dict | None:
    clean = text.strip()
    if clean.startswith("```"):
        clean = re.sub(r'^```\w*\n?', '', clean)
        clean = re.sub(r'\n?```\s*$', '', clean)
        clean = clean.strip()

    think_m = re.search(r'THINK[：:]\s*(.+?)(?=\n\s*GOAL[：:]|\n\s*CMD[：:]|\n\s*RISK[：:]|\n\s*CONTROL[：:]|\Z)', clean, re.DOTALL | re.IGNORECASE)
    goal_m = re.search(r'GOAL[：:]\s*(.+)', clean, re.IGNORECASE)
    cmd_m = re.search(r'CMD[：:]\s*(.+)', clean, re.IGNORECASE)
    risk_m = re.search(r'RISK[：:]\s*(.+)', clean, re.IGNORECASE)
    control_m = re.search(r'CONTROL[：:]\s*(AUTO|CONFIRM|ASK|DONE)', clean, re.IGNORECASE)
    summary_m = re.search(r'SUMMARY[：:]\s*(.+)', clean, re.DOTALL | re.IGNORECASE)

    control = control_m.group(1).strip().upper() if control_m else "CONFIRM"
    is_done = control == "DONE"

    if is_done:
        return {
            "think": think_m.group(1).strip() if think_m else "",
            "goal": "任务完成",
            "command": "",
            "risk": "安全",
            "control": "DONE",
            "summary": summary_m.group(1).strip() if summary_m else "任务完成",
        }

    command = cmd_m.group(1).strip() if cmd_m else ""

    if command.startswith('`') and command.endswith('`'):
        command = command[1:-1].strip()

    if not command and control not in ("ASK",):
        return None

    return {
        "think": think_m.group(1).strip() if think_m else "",
        "goal": goal_m.group(1).strip() if goal_m else "",
        "command": command,
        "risk": risk_m.group(1).strip() if risk_m else "安全",
        "control": control,
        "summary": "",
    }


def _is_forced_confirm(command: str) -> bool:
    for pattern in _FORCED_CONFIRM_PATTERNS:
        if re.search(pattern, command):
            return True
    for path in _FORCED_CONFIRM_PATHS:
        if path in command and ('tee' in command or 'cat >' in command or 'echo' in command or 'write' in command):
            return True
    return False


def _resolve_control(step: dict) -> str:
    control = step.get("control", "CONFIRM")
    command = step.get("command", "")
    risk = step.get("risk", "安全")

    if control == "DONE" or control == "ASK":
        return control

    if control == "AUTO":
        if step.get("risk") in ("中", "高"):
            return "CONFIRM"
        if _is_forced_confirm(command):
            return "CONFIRM"
        return "AUTO"

    return "CONFIRM"


def _print_plan(reply: str, out):
    plan_start = reply.find("PLAN_START")
    plan_end = reply.find("PLAN_END")
    if plan_start != -1 and plan_end != -1:
        plan = reply[plan_start + len("PLAN_START"):plan_end].strip()
        out(f"\n{'=' * 50}")
        out(plan)
        out(f"{'=' * 50}")
        after_plan = reply[plan_end + len("PLAN_END"):].strip()
        if after_plan:
            out(f"\n  {after_plan}")
    else:
        out(f"\n  {reply[:500]}")


def _print_step(step_num: int, step: dict, out):
    risk_icon = {"安全": "*", "低": "*", "中": "!", "高": "!!"}.get(step.get("risk", ""), "*")
    control_label = {"AUTO": "自动执行", "CONFIRM": "需确认", "ASK": "提问"}.get(step.get("control", ""), "")
    out(f"\n{'─' * 50}")
    out(f"  Step {step_num}")
    if step.get("think"):
        out(f"  THINK: {step['think'][:200]}")
    out(f"  GOAL:  {step.get('goal', '?')}")
    if step.get("command"):
        out(f"  CMD:   {step['command']}")
    out(f"  RISK:  {step.get('risk', '?')} {risk_icon}  [{control_label}]")


def _print_result(result: ExecResult, out, already_streamed: bool = False):
    status = "[OK]" if result.exit_code == 0 else f"[X] (exit {result.exit_code})"
    out(f"\n{status} | {result.duration_ms}ms")
    if already_streamed:
        if result.stderr and result.exit_code != 0:
            out(f"[stderr] {result.stderr}")
        return
    if result.stdout:
        out(result.stdout.strip())
    if result.stderr and result.exit_code != 0:
        out(f"[stderr] {result.stderr}")


def _compress_messages(messages: list[dict], task: str, out) -> list[dict]:
    if len(messages) <= _COMPRESS_THRESHOLD * 2 + 2:
        return messages

    system_msg = messages[0]
    rest = messages[1:]

    keep_old = _COMPRESS_THRESHOLD - _COMPRESS_KEEP_RECENT
    keep_recent = _COMPRESS_KEEP_RECENT * 2

    old = rest[:keep_old * 2]
    recent = rest[-(keep_recent):]

    completed_steps = []
    for i in range(0, len(old), 2):
        if i + 1 < len(old):
            assistant = old[i].get("content", "")
            observe = old[i + 1].get("content", "")
            step = _parse_step(assistant)
            goal = step["goal"] if step else ""
            exit_code = "0"
            key_info = ""
            for line in observe.split("\n"):
                if line.startswith("退出码:"):
                    exit_code = line.split(":")[1].strip()
                if "错误" in line or "error" in line.lower() or "fail" in line.lower():
                    key_info = line.strip()[:100]
            status = "OK" if exit_code == "0" else f"FAIL({exit_code})"
            detail = f" — {key_info}" if key_info else ""
            if goal:
                completed_steps.append(f"  - {goal}: {status}{detail}")

    summary_lines = "\n".join(completed_steps) if completed_steps else "(早期步骤已执行)"
    summary = (
        f"[上下文压缩] 原始任务: {task}\n"
        f"已完成 {len(completed_steps)} 步:\n{summary_lines}\n"
        f"以上步骤已执行完毕，继续后续步骤。"
    )

    compressed = [system_msg]
    compressed.append({"role": "user", "content": summary})
    compressed.extend(recent)

    old_chars = _count_messages_chars(messages)
    new_chars = _count_messages_chars(compressed)
    out(f"\n  [context compressed: {len(messages)} -> {len(compressed)} msgs, {old_chars} -> {new_chars} chars]\n")

    return compressed


async def _exec_with_heartbeat(connector, command, out):
    last_output_time = _time.monotonic()
    idle_dots = 0
    exec_done = asyncio.Event()
    stream_buf = []

    def _on_output(text):
        nonlocal last_output_time, idle_dots
        last_output_time = _time.monotonic()
        if idle_dots > 0:
            out("\r" + " " * (idle_dots + 20) + "\r")
            idle_dots = 0
        stream_buf.append(text)
        out(text)

    async def _heartbeat():
        nonlocal idle_dots
        while not exec_done.is_set():
            await asyncio.sleep(3)
            if exec_done.is_set():
                break
            elapsed = int(_time.monotonic() - last_output_time)
            if elapsed >= 5:
                idle_dots += 1
                out(f"\r  [waiting... {elapsed}s]")

    hb = asyncio.ensure_future(_heartbeat())
    try:
        result = await connector.exec_streaming(
            command, timeout=300, on_output=_on_output,
        )
    finally:
        exec_done.set()
        hb.cancel()
        try:
            await hb
        except (asyncio.CancelledError, Exception):
            pass

    return result, stream_buf


async def run_task(
    task: str,
    connector: Connector,
    probe_data: dict,
    auto_confirm: bool = False,
    context: str = "",
    session_memory: list[str] | None = None,
    output: "callable | None" = None,
    input_callback: "callable | None" = None,
) -> str:
    out = output or print
    inp = input_callback or (lambda prompt: input(prompt).strip())

    env_info = build_env_info(probe_data)
    context_section = build_context_section(context, session_memory)
    system = SYSTEM_PROMPT.format(env_info=env_info, context_section=context_section)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": task},
    ]

    step_count = 0
    executed_count = 0
    compress_count = 0
    planned = False

    while step_count < _MAX_STEPS:

        if len(messages) > _COMPRESS_THRESHOLD * 2 and _count_messages_chars(messages) > 30000:
            messages = _compress_messages(messages, task, out)
            compress_count += 1

        out("  [thinking...]")
        try:
            reply = chat(messages)
        except Exception as e:
            out(f"\n[X] LLM call failed: {e}")
            return f"LLM error: {e}"

        if not reply or not reply.strip():
            out("\n  [!] LLM returned empty, retrying...\n")
            continue

        if not planned and "PLAN_START" in reply:
            _print_plan(reply, out)
            planned = True

            user_input = inp("\n  确认执行此方案？[Y/调整意见]: ")
            if user_input.lower() in ("y", "yes", ""):
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content": "方案已确认，开始执行第一步。"})
                continue
            else:
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content": f"用户反馈：{user_input}。请调整方案。"})
                planned = False
                out("  [feedback] 调整方案...\n")
                continue

        step = _parse_step(reply)
        if not step:
            messages.append({"role": "assistant", "content": reply})
            out(f"\n  AI: {reply[:300]}")
            messages.append({
                "role": "user",
                "content": "请严格按格式输出下一步: THINK/GOAL/CMD/RISK/CONTROL，或 CONTROL: DONE 结束。",
            })
            continue

        control = _resolve_control(step)

        step_count += 1

        if step["control"] == "DONE":
            out(f"\n{'=' * 50}")
            out(f"[DONE] | {executed_count} commands executed (compressed {compress_count}x)")
            if step.get("summary"):
                out(f"       {step['summary']}")
            out("")
            return step.get("summary", "task completed")

        _print_step(step_count, step, out)

        if control == "ASK":
            if step.get("think"):
                out(f"  {step['think']}")
            user_answer = inp("  > ")
            messages.append({"role": "assistant", "content": reply})
            messages.append({"role": "user", "content": f"用户回答: {user_answer}"})
            out("")
            continue

        if control == "CONFIRM" and not auto_confirm:
            user_input = inp("  [Y]执行 / [n]跳过 / [q]退出 / <反馈>: ").lower()
            if user_input == "q":
                out("  [ABORT] task cancelled\n")
                return f"user aborted at step {step_count}"
            if user_input == "n":
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content": f"user rejected: {step['command']}. adjust plan."})
                out("  skipped\n")
                continue
            if user_input not in ("y", "yes", ""):
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content": f"user feedback (do NOT execute previous command, adjust based on feedback): {user_input}"})
                out("  [feedback] adjusting...\n")
                continue
        elif control == "AUTO":
            out("  [auto] executing...")

        messages.append({"role": "assistant", "content": reply})

        try:
            result, stream_buf = await _exec_with_heartbeat(
                connector, step["command"], out,
            )
        except KeyboardInterrupt:
            out("\n\n  ⏸ 用户中断（Ctrl+C）")
            feedback = inp("  [r]重试 / [k]终止 / <反馈意见>: ")
            if feedback.lower() == "k":
                out("  [ABORT] task cancelled\n")
                return f"user aborted at step {step_count}"
            else:
                messages.append({"role": "user", "content": f"用户中断了当前步骤（{step['command']}），反馈：{feedback}。请根据反馈调整。"})
                out("  [feedback] adjusting...\n")
                continue

        if result.exit_code == -2:
            out("\n\n  ⏸ 命令被中断")
            feedback = inp("  [r]重试 / [k]终止 / <反馈意见>: ")
            if feedback.lower() == "k":
                out("  [ABORT] task cancelled\n")
                return f"user aborted at step {step_count}"
            if feedback.lower() in ("r", "y", "yes", ""):
                out("  [retry] retrying...\n")
                try:
                    result, stream_buf = await _exec_with_heartbeat(
                        connector, step["command"], out,
                    )
                except KeyboardInterrupt:
                    out("\n  [ABORT] 二次中断\n")
                    return f"user aborted at step {step_count}"
                if result.exit_code == -2:
                    out("\n  [ABORT] 二次中断\n")
                    return f"user aborted at step {step_count}"
            else:
                messages.append({"role": "user", "content": f"用户中断了当前步骤（{step['command']}），反馈：{feedback}。请根据反馈调整。"})
                out("  [feedback] adjusting...\n")
                continue

        if stream_buf:
            out("")

        executed_count += 1
        _print_result(result, out, already_streamed=bool(stream_buf))

        observe = (
            f"命令: {result.command}\n"
            f"退出码: {result.exit_code}\n"
            f"耗时: {result.duration_ms}ms\n"
            f"输出:\n{_truncate(result.stdout)}\n"
        )
        if result.stderr and result.exit_code != 0:
            observe += f"错误输出:\n{_truncate(result.stderr)}\n"

        messages.append({"role": "user", "content": observe})

    return f"max steps ({_MAX_STEPS}) reached, task incomplete"
