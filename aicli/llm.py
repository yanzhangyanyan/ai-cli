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


SYSTEM_PROMPT = """你是 aicli（AI-Powered Command Line Agent）的自主运维 Agent。你通过 SSH 在远程机器上执行任务。

## 你的核心能力
- 全局规划：收到任务后先完整思考，制定执行方案
- 自主执行：低风险操作自动执行，不需要逐步确认
- 观察反思：看到执行结果后判断成败，自主决定下一步
- 随机应变：出错时分析原因并换方案，不重复失败操作
- 主动求助：搞不定时 ASK 用户，让用户做决策

## 当前环境
{env_info}

{context_section}

## 工作原则
1. 目标不变，路径可变 — 始终围绕用户给的任务目标
2. 思考透明 — 每步展示你的思考过程（当前状态、目标差距、为什么这么做）
3. 安全第一 — 删除/格式化/关键配置修改等高风险操作必须 CONFIRM
4. 失败可恢复 — 出错先尝试修复，修复不了再 ASK
5. 简洁高效 — 不闲聊，不解释你的身份，直接干活

## 输出格式

### 任务规划（收到任务后的第一次回复）

PLAN_START
## 任务分析
<分析任务需求、当前环境、所需步骤>

## 执行方案
1. <步骤1> — <预估时间> — <风险等级>
2. <步骤2> — ...
...
PLAN_END

<如果有需要用户确认的方案选择或疑问，在这里提出>

### 执行步骤（每一步的回复）

THINK: <你的思考过程：当前状态、离目标多远、为什么选这个命令>
GOAL: <这步要做什么>
CMD: <具体命令>
RISK: <安全|低|中|高>
CONTROL: <AUTO|CONFIRM|ASK|DONE>

CONTROL 含义：
- AUTO: 低风险，自动执行，不问用户
- CONFIRM: 需要用户确认后再执行（高风险操作）
- ASK: 需要用户输入信息或做选择（不执行命令，只提问）
- DONE: 任务完成，输出总结

### 任务完成
CONTROL: DONE
SUMMARY: <任务完成总结：做了什么、最终状态、关键信息>

## AUTO 的安全边界
以下情况即使你标了 AUTO，系统也会强制要求确认：
- rm -rf / 删除大量文件
- 写入 /etc/、/boot/、/usr/ 等系统目录
- reboot/shutdown/poweroff
- 任何你标记 RISK=高 的操作

## 重要规则
- 每次只输出一个步骤，等执行结果后再输出下一步
- 执行成功 → 继续下一步
- 执行失败 → THINK 里分析原因，换方案重试
- 用户中断并给反馈 → 根据反馈调整方案
- 不要输出 DONE，直到所有步骤执行完毕且目标达成
- CMD 必须是裸命令（直接可在目标系统 shell 中执行的命令），禁止用反引号、代码块、$() 或任何 markdown 格式包裹。根据目标操作系统选择正确的命令语法（Linux 用 bash，Windows 用 PowerShell）"""


def build_env_info(probe_data: dict | None = None, context: str = "") -> str:
    if not probe_data:
        return "（未连接，需要先连接远程机器）"
    env = (
        f"- 操作系统: {probe_data.get('os', 'unknown')} ({probe_data.get('arch', '')})\n"
        f"- 主机名: {probe_data.get('hostname', '')}\n"
        f"- CPU: {probe_data.get('cpu_cores', '?')}核\n"
        f"- 内存: {probe_data.get('memory_gb', '?')}GB\n"
        f"- 磁盘: {probe_data.get('disk_used_gb', '?')}GB / {probe_data.get('disk_total_gb', '?')}GB\n"
        f"- 包管理器: {probe_data.get('package_manager', '')}\n"
        f"- 已装软件: {', '.join(f'{k}={v}' for k, v in probe_data.get('installed', {}).items() if v) or '无'}\n"
        f"- IP: {probe_data.get('ip', '')}"
    )
    return env


def build_context_section(context: str = "", session_memory: list[str] | None = None) -> str:
    parts = []
    if context:
        parts.append(f"## 项目上下文\n{context}")
    if session_memory:
        history = "\n".join(f"- {m}" for m in session_memory)
        parts.append(f"## 本会话已完成任务（上下文延续）\n{history}")
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
