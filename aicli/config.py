import json
import os
from pathlib import Path
from openai import OpenAI

from .i18n import t, get_lang

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
    print("  aiCLI — LLM Setup Wizard")
    print("=" * 50)
    print()
    print("  aiCLI needs an LLM API to provide AI capabilities.")
    print("  Supports any OpenAI-compatible API (LiteLLM / OpenAI / Zhipu / ...)")
    print()

    base_url = input(f"  API URL [{_DEFAULT_BASE_URL}]: ").strip()
    if not base_url:
        base_url = _DEFAULT_BASE_URL

    api_key = input("  API Key: ").strip()

    print()
    print(f"  Fetching available models...")
    models = list_available_models(base_url, api_key)
    if not models or models[0].get("id", "").startswith("error"):
        err = models[0]["id"] if models else "unknown"
        print(f"  Connection failed: {err}")
        print()
        manual = input("  Enter model name manually (leave empty to cancel): ").strip()
        if not manual:
            print("  Setup cancelled.")
            return False
        save_config({"base_url": base_url, "api_key": api_key, "model": manual})
        print(f"\n  OK model configured: {manual}")
        print(f"  Config saved to: {_CONFIG_PATH}")
        return True

    print(f"  Found {len(models)} models:")
    print()
    for i, m in enumerate(models, 1):
        print(f"    [{i:2d}] {m['id']}")

    print()
    idx = input(f"  Select model number [1]: ").strip()
    if not idx:
        idx = "1"
    try:
        selected = models[int(idx) - 1]["id"]
    except (ValueError, IndexError):
        selected = models[0]["id"]

    save_config({"base_url": base_url, "api_key": api_key, "model": selected})

    print()
    print(f"  OK setup complete!")
    print(f"     API:   {base_url}")
    print(f"     Model: {selected}")
    print(f"     Config: {_CONFIG_PATH}")
    print()
    return True


def config_command(args: list[str]):
    cfg = load_config()

    if not args or args[0] == "show":
        if not cfg:
            print("  Not configured. Run aicli to start the setup wizard.")
            return
        print(f"  API:      {cfg.get('base_url', '?')}")
        print(f"  Model:    {cfg.get('model', '?')}")
        print(f"  Key:      {'*' * 8}{cfg.get('api_key', '')[-4:]}")
        print(f"  Thinking: {'on' if cfg.get('thinking', False) else 'off'}")
        print(f"  File:     {_CONFIG_PATH}")
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
            print(f"  OK model switched to: {new_model}")
        else:
            base_url = cfg.get("base_url", "")
            api_key = cfg.get("api_key", "")
            if not base_url:
                print("  No API configured. Run aicli config setup first.")
                return
            print(f"  Fetching available models...")
            models = list_available_models(base_url, api_key)
            if not models or models[0].get("id", "").startswith("error"):
                print("  Failed to fetch models. Check API connection.")
                return
            for i, m in enumerate(models, 1):
                current = " <--" if m["id"] == cfg.get("model") else ""
                print(f"    [{i:2d}] {m['id']}{current}")
            print()
            idx = input("  Select number to switch (empty to cancel): ").strip()
            if idx:
                try:
                    cfg["model"] = models[int(idx) - 1]["id"]
                    save_config(cfg)
                    print(f"  OK switched to: {cfg['model']}")
                except (ValueError, IndexError):
                    print("  Invalid selection")

    elif cmd == "thinking":
        if len(args) > 1:
            val = args[1].lower() in ("on", "true", "1", "yes")
        else:
            val = not cfg.get("thinking", False)
        cfg["thinking"] = val
        save_config(cfg)
        print(f"  OK thinking mode: {'on' if val else 'off'}")

    elif cmd == "api":
        new_url = input(f"  API URL [{cfg.get('base_url', '')}]: ").strip()
        new_key = input(f"  API Key [***]: ").strip()
        if new_url:
            cfg["base_url"] = new_url
        if new_key:
            cfg["api_key"] = new_key
        save_config(cfg)
        print(f"  OK API updated")

    elif cmd == "reset":
        if os.path.exists(_CONFIG_PATH):
            os.remove(_CONFIG_PATH)
            print("  OK config cleared")
        else:
            print("  No config file")

    else:
        print("  Usage: config [show|setup|model|thinking|api|reset]")
