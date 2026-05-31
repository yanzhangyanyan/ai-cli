import os
from openai import OpenAI
from .config import get_llm_config, is_configured


def get_client() -> OpenAI:
    c = get_llm_config()
    import httpx
    return OpenAI(
        base_url=c["base_url"],
        api_key=c["api_key"] or "sk-no-key",
        timeout=httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0),
    )


def get_model() -> str:
    return get_llm_config()["model"]


SYSTEM_PROMPT = """You are the autonomous ops Agent of aiCLI (AI-Powered Command Line Agent). You execute tasks via SSH on remote machines or locally.

## Core Capabilities
- Global planning: Think through the entire task before acting, create an execution plan
- Autonomous execution: Auto-execute low-risk operations without step-by-step confirmation
- Observe and reflect: Evaluate results after each step, decide next action autonomously
- Adaptive: Analyze failures and switch approaches, never repeat failed operations
- Ask for help: Use ASK when stuck, let the user make decisions

## Current Environment
{env_info}

{context_section}

## Working Principles
1. Goal unchanged, path flexible — Always focus on the user's task goal
2. Transparent thinking — Show your thought process each step (current state, gap to goal, why this approach)
3. Safety first — DELETE/FORMAT/critical config changes must use CONFIRM
4. Recoverable failures — Try to fix errors first, ASK only when recovery fails
5. Concise and efficient — No small talk, no identity explanation, just get work done

## Output Format

### Task Planning (first reply after receiving a task)

PLAN_START
## Task Analysis
<Analyze task requirements, current environment, required steps>

## Execution Plan
1. <Step 1> — <estimated time> — <risk level>
2. <Step 2> — ...
...
PLAN_END

<If there are options or questions for the user, present them here>

### Execution Steps (each step reply)

THINK: <Your thought process: current state, distance to goal, why this command>
GOAL: <What this step accomplishes>
CMD: <Exact command>
RISK: <safe|low|medium|high>
CONTROL: <AUTO|CONFIRM|ASK|DONE>

CONTROL meanings:
- AUTO: Low risk, execute automatically, don't ask user
- CONFIRM: Requires user confirmation before executing (high-risk operations)
- ASK: Need user input or decision (no command execution, just asking)
- DONE: Task complete, output summary

### Task Complete
CONTROL: DONE
SUMMARY: <Task completion summary: what was done, final state, key information>

## AUTO Safety Boundary
The following situations will force CONFIRM even if you mark AUTO:
- rm -rf / mass file deletion
- Writing to /etc/, /boot/, /usr/ and other system directories
- reboot/shutdown/poweroff
- Any operation you mark as RISK=high

## Important Rules
- Output only one step at a time, wait for execution result before outputting the next step
- Execution success → continue to next step
- Execution failure → analyze cause in THINK, retry with different approach
- User interrupt with feedback → adjust plan based on feedback
- Do not output DONE until all steps are completed and the goal is achieved
- CMD must be a bare command (directly executable in the target system shell), no backticks, code blocks, $() or any markdown wrapping. Use correct command syntax for the target OS (bash for Linux, PowerShell for Windows)"""


def build_env_info(probe_data: dict | None = None, context: str = "") -> str:
    if not probe_data:
        return "(Not connected, need to connect to a remote machine first)"
    env = (
        f"- OS: {probe_data.get('os', 'unknown')} ({probe_data.get('arch', '')})\n"
        f"- Hostname: {probe_data.get('hostname', '')}\n"
        f"- CPU: {probe_data.get('cpu_cores', '?')} cores\n"
        f"- Memory: {probe_data.get('memory_gb', '?')}GB\n"
        f"- Disk: {probe_data.get('disk_used_gb', '?')}GB / {probe_data.get('disk_total_gb', '?')}GB\n"
        f"- Package manager: {probe_data.get('package_manager', '')}\n"
        f"- Installed: {', '.join(f'{k}={v}' for k, v in probe_data.get('installed', {}).items() if v) or 'none'}\n"
        f"- IP: {probe_data.get('ip', '')}"
    )
    return env


def build_context_section(context: str = "", session_memory: list[str] | None = None) -> str:
    parts = []
    if context:
        parts.append(f"## Project Context\n{context}")
    if session_memory:
        history = "\n".join(f"- {m}" for m in session_memory)
        parts.append(f"## Completed Tasks This Session (context continuation)\n{history}")
    return "\n\n".join(parts)


def chat(messages: list[dict], temperature: float = 0.3, retries: int = 2) -> str:
    client = get_client()
    llm_cfg = get_llm_config()
    model = llm_cfg["model"]
    for attempt in range(retries + 1):
        try:
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }
            if not llm_cfg.get("thinking") and "glm" in model.lower():
                kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
            resp = client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""
        except Exception as e:
            if attempt < retries:
                import time
                err_msg = str(e)[:80]
                print(f"\r  [LLM retry {attempt + 1}/{retries}: {err_msg}]", flush=True)
                time.sleep(2 * (attempt + 1))
                continue
            raise
