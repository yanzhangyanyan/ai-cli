import json
import os
from pathlib import Path
from openai import OpenAI

_CONFIG_DIR = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
_CONFIG_PATH = os.path.join(_CONFIG_DIR, "aicli", "config.json")

_DEFAULT_BASE_URL = "http://localhost:4000/v1"


def _ensure_dir():
    d = os.path.dirname(_CONFIG_PATH)
    if not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def load_config() -> dict:
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(cfg: dict):
    _ensure_dir()
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get_llm_config() -> dict:
    cfg = load_config()
    thinking_raw = os.environ.get("AICLI_LLM_THINKING", str(cfg.get("thinking", False)))
    thinking = thinking_raw in (True, "true", "True", "1")
    return {
        "base_url": os.environ.get("AICLI_LLM_BASE_URL", cfg.get("base_url", "")),
        "api_key": os.environ.get("AICLI_LLM_API_KEY", cfg.get("api_key", "")),
        "model": os.environ.get("AICLI_LLM_MODEL", cfg.get("model", "")),
        "thinking": thinking,
    }


def is_configured() -> bool:
    c = get_llm_config()
    return bool(c["base_url"] and c["model"])


def list_available_models(base_url: str, api_key: str) -> list[dict]:
    try:
        client = OpenAI(base_url=base_url, api_key=api_key or "sk-no-key")
        resp = client.models.list()
        models = []
        for m in resp.data:
            models.append({"id": m.id})
        return models
    except Exception as e:
        return [{"id": f"error: {e}"}]


def first_run_setup():
    print()
    print("=" * 50)
    print("  aicli 首次运行 — LLM 配置向导")
    print("=" * 50)
    print()
    print("  aicli 需要连接大模型 API 来提供 AI 能力。")
    print("  支持任何 OpenAI 兼容 API（LiteLLM / OpenAI / 智谱 / ...）")
    print()

    base_url = input(f"  API 地址 [{_DEFAULT_BASE_URL}]: ").strip()
    if not base_url:
        base_url = _DEFAULT_BASE_URL

    api_key = input("  API Key: ").strip()

    print()
    print(f"  正在获取可用模型...")
    models = list_available_models(base_url, api_key)
    if not models or models[0].get("id", "").startswith("error"):
        err = models[0]["id"] if models else "unknown"
        print(f"  连接失败: {err}")
        print()
        manual = input("  输入模型名称手动配置（留空退出）: ").strip()
        if not manual:
            print("  配置取消。")
            return False
        save_config({"base_url": base_url, "api_key": api_key, "model": manual})
        print(f"\n  OK 已配置模型: {manual}")
        print(f"  配置保存到: {_CONFIG_PATH}")
        return True

    print(f"  找到 {len(models)} 个模型:")
    print()
    for i, m in enumerate(models, 1):
        print(f"    [{i:2d}] {m['id']}")

    print()
    idx = input(f"  选择模型编号 [1]: ").strip()
    if not idx:
        idx = "1"
    try:
        selected = models[int(idx) - 1]["id"]
    except (ValueError, IndexError):
        selected = models[0]["id"]

    save_config({"base_url": base_url, "api_key": api_key, "model": selected})

    print()
    print(f"  OK 配置完成!")
    print(f"     API:  {base_url}")
    print(f"     模型: {selected}")
    print(f"     配置: {_CONFIG_PATH}")
    print()
    return True


def config_command(args: list[str]):
    cfg = load_config()

    if not args or args[0] == "show":
        if not cfg:
            print("  未配置。运行 aicli 进入首次配置向导。")
            return
        print(f"  API:      {cfg.get('base_url', '?')}")
        print(f"  模型:     {cfg.get('model', '?')}")
        print(f"  Key:      {'*' * 8}{cfg.get('api_key', '')[-4:]}")
        print(f"  思考模式: {'开启' if cfg.get('thinking', False) else '关闭'}")
        print(f"  文件:     {_CONFIG_PATH}")
        return

    cmd = args[0]

    if cmd == "setup":
        first_run_setup()
        return

    if cmd == "model":
        if len(args) > 1:
            new_model = args[1]
            cfg["model"] = new_model
            save_config(cfg)
            print(f"  OK 模型已切换为: {new_model}")
        else:
            base_url = cfg.get("base_url", "")
            api_key = cfg.get("api_key", "")
            if not base_url:
                print("  未配置 API，先运行 aicli config setup")
                return
            print(f"  正在获取可用模型...")
            models = list_available_models(base_url, api_key)
            if not models or models[0].get("id", "").startswith("error"):
                print("  获取失败，请检查 API 连接")
                return
            for i, m in enumerate(models, 1):
                current = " <--" if m["id"] == cfg.get("model") else ""
                print(f"    [{i:2d}] {m['id']}{current}")
            print()
            idx = input("  选择编号切换（留空取消）: ").strip()
            if idx:
                try:
                    cfg["model"] = models[int(idx) - 1]["id"]
                    save_config(cfg)
                    print(f"  OK 已切换为: {cfg['model']}")
                except (ValueError, IndexError):
                    print("  无效选择")

    elif cmd == "thinking":
        if len(args) > 1:
            val = args[1].lower() in ("on", "true", "1", "yes", "开启")
        else:
            val = not cfg.get("thinking", False)
        cfg["thinking"] = val
        save_config(cfg)
        print(f"  OK 思考模式: {'开启' if val else '关闭'}")

    elif cmd == "api":
        new_url = input(f"  API 地址 [{cfg.get('base_url', '')}]: ").strip()
        new_key = input(f"  API Key [***]: ").strip()
        if new_url:
            cfg["base_url"] = new_url
        if new_key:
            cfg["api_key"] = new_key
        save_config(cfg)
        print(f"  OK API 已更新")

    elif cmd == "reset":
        if os.path.exists(_CONFIG_PATH):
            os.remove(_CONFIG_PATH)
            print("  OK 配置已清除")
        else:
            print("  无配置文件")

    else:
        print("  用法: config [show|setup|model|thinking|api|reset]")
