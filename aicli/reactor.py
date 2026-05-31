import asyncio
import re
import sys
import time as _time

from .connectors.base import Connector, ExecResult
from .llm import SYSTEM_PROMPT, build_env_info, build_context_section, chat
from .session import SessionManager
from .i18n import t

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
    return text[:head] + f"\n... [truncated, {len(text)} chars total, keeping head/tail] ...\n" + text[-tail:]


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
            "goal": "task completed",
            "command": "",
            "risk": "safe",
            "control": "DONE",
            "summary": summary_m.group(1).strip() if summary_m else "task completed",
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
        "risk": risk_m.group(1).strip() if risk_m else "safe",
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

    if control == "DONE" or control == "ASK":
        return control

    if control == "AUTO":
        if step.get("risk") in ("medium", "high", "中", "高"):
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
        sep = "=" * 50
        out(t("plan_title", sep=sep))
        out(plan)
        out(sep)
        after_plan = reply[plan_end + len("PLAN_END"):].strip()
        if after_plan:
            out(f"\n  {after_plan}")
    else:
        out(f"\n  {reply[:500]}")


def _print_step(step_num: int, step: dict, out):
    risk_icon = {"safe": "*", "low": "*", "medium": "!", "high": "!!",
                 "安全": "*", "低": "*", "中": "!", "高": "!!"}.get(step.get("risk", ""), "*")
    risk_val = step.get("risk", "?")
    control_val = step.get("control", "")
    control_label = {"AUTO": t("auto_exec").strip(), "CONFIRM": "confirm", "ASK": "ask"}.get(control_val, control_val)
    sep = "─" * 50
    out(t("step_header", sep=sep))
    out(t("step_num", n=step_num))
    if step.get("think"):
        out(t("step_think", think=step['think'][:200]))
    out(t("step_goal", goal=step.get('goal', '?')))
    if step.get("command"):
        out(t("step_cmd", cmd=step['command']))
    out(t("step_risk", risk=risk_val, icon=risk_icon, label=control_label))


def _print_result(result: ExecResult, out, already_streamed: bool = False):
    if result.exit_code == 0:
        out(t("result_ok", ms=result.duration_ms))
    else:
        out(t("result_fail", code=result.exit_code, ms=result.duration_ms))
    if already_streamed:
        if result.stderr and result.exit_code != 0:
            out(t("stderr_label", stderr=result.stderr))
        return
    if result.stdout:
        out(result.stdout.strip())
    if result.stderr and result.exit_code != 0:
        out(t("stderr_label", stderr=result.stderr))


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
                if line.startswith("exit_code:") or line.startswith("退出码:"):
                    exit_code = line.split(":")[-1].strip()
                if "error" in line.lower() or "fail" in line.lower() or "错误" in line:
                    key_info = line.strip()[:100]
            status = "OK" if exit_code == "0" else f"FAIL({exit_code})"
            detail = f" — {key_info}" if key_info else ""
            if goal:
                completed_steps.append(f"  - {goal}: {status}{detail}")

    summary_lines = "\n".join(completed_steps) if completed_steps else "(earlier steps completed)"
    summary = (
        f"[Context compression] Original task: {task}\n"
        f"Completed {len(completed_steps)} steps:\n{summary_lines}\n"
        f"The above steps are complete. Continue with remaining steps."
    )

    compressed = [system_msg]
    compressed.append({"role": "user", "content": summary})
    compressed.extend(recent)

    old_chars = _count_messages_chars(messages)
    new_chars = _count_messages_chars(compressed)
    out(t("compressed", old=len(messages), new=len(compressed), old_chars=old_chars, new_chars=new_chars))

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
                out(t("waiting", sec=elapsed))

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

        out(t("thinking"))
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

            user_input = inp(t("plan_confirm"))
            if user_input.lower() in ("y", "yes", ""):
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content": "Plan confirmed. Start executing the first step."})
                continue
            else:
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content": f"User feedback: {user_input}. Please adjust the plan."})
                planned = False
                out(t("feedback"))
                continue

        step = _parse_step(reply)
        if not step:
            messages.append({"role": "assistant", "content": reply})
            out(f"\n  AI: {reply[:300]}")
            messages.append({
                "role": "user",
                "content": "Please strictly follow the format for the next step: THINK/GOAL/CMD/RISK/CONTROL, or CONTROL: DONE to finish.",
            })
            continue

        control = _resolve_control(step)

        step_count += 1

        if step["control"] == "DONE":
            sep = "=" * 50
            out(t("done_header", sep=sep))
            out(t("done_summary", count=executed_count, comp=compress_count))
            if step.get("summary"):
                out(f"       {step['summary']}")
            out(t("done_footer", sep=sep))
            return step.get("summary", "task completed")

        _print_step(step_count, step, out)

        if control == "ASK":
            if step.get("think"):
                out(f"  {step['think']}")
            user_answer = inp("  > ")
            messages.append({"role": "assistant", "content": reply})
            messages.append({"role": "user", "content": f"User answer: {user_answer}"})
            out("")
            continue

        if control == "CONFIRM" and not auto_confirm:
            user_input = inp(t("confirm_exec")).lower()
            if user_input == "q":
                out(t("aborted"))
                return f"user aborted at step {step_count}"
            if user_input == "n":
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content": f"user rejected: {step['command']}. adjust plan."})
                out(t("skipped"))
                continue
            if user_input not in ("y", "yes", ""):
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content": f"user feedback (do NOT execute previous command, adjust based on feedback): {user_input}"})
                out(t("feedback"))
                continue
        elif control == "AUTO":
            out(t("auto_exec"))

        messages.append({"role": "assistant", "content": reply})

        try:
            result, stream_buf = await _exec_with_heartbeat(
                connector, step["command"], out,
            )
        except KeyboardInterrupt:
            out(t("user_interrupt"))
            feedback = inp(t("interrupt_choice"))
            if feedback.lower() == "k":
                out(t("aborted"))
                return f"user aborted at step {step_count}"
            else:
                messages.append({"role": "user", "content": f"User interrupted current step ({step['command']}), feedback: {feedback}. Please adjust based on feedback."})
                out(t("feedback"))
                continue

        if result.exit_code == -2:
            out("\n\n  ⏸ Command interrupted")
            feedback = inp(t("interrupt_choice"))
            if feedback.lower() == "k":
                out(t("aborted"))
                return f"user aborted at step {step_count}"
            if feedback.lower() in ("r", "y", "yes", ""):
                out("  [retry] retrying...\n")
                try:
                    result, stream_buf = await _exec_with_heartbeat(
                        connector, step["command"], out,
                    )
                except KeyboardInterrupt:
                    out("\n  [ABORT] second interrupt\n")
                    return f"user aborted at step {step_count}"
                if result.exit_code == -2:
                    out("\n  [ABORT] second interrupt\n")
                    return f"user aborted at step {step_count}"
            else:
                messages.append({"role": "user", "content": f"User interrupted current step ({step['command']}), feedback: {feedback}. Please adjust based on feedback."})
                out(t("feedback"))
                continue

        if stream_buf:
            out("")

        executed_count += 1
        _print_result(result, out, already_streamed=bool(stream_buf))

        observe = (
            f"command: {result.command}\n"
            f"exit_code: {result.exit_code}\n"
            f"duration: {result.duration_ms}ms\n"
            f"output:\n{_truncate(result.stdout)}\n"
        )
        if result.stderr and result.exit_code != 0:
            observe += f"stderr:\n{_truncate(result.stderr)}\n"

        messages.append({"role": "user", "content": observe})

    return f"max steps ({_MAX_STEPS}) reached, task incomplete"
