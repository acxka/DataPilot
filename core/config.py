# -*- coding: utf-8 -*-
"""配置加载：从 .env 读取模型与数据库配置（零第三方依赖）。"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(ROOT, ".env")


def load_env(path=ENV_PATH):
    """极简 .env 解析，不覆盖已存在的系统环境变量。"""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())


load_env()
DB_PATH = os.path.join(ROOT, "data", "retail.db")
RUNS_DIR = os.path.join(ROOT, "runs")

_primary = os.environ.get("PRIMARY_PROVIDER", "deepseek").strip()


def _provider(name):
    if name == "deepseek":
        return {
            "name": "deepseek",
            "base_url": os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            "api_key": os.environ.get("DEEPSEEK_API_KEY", ""),
            "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro"),
        }
    if name == "hetune":
        return {
            "name": "hetune",
            "base_url": os.environ.get("HETUNE_BASE_URL", "https://api.hetune.top"),
            "api_key": os.environ.get("HETUNE_API_KEY", ""),
            "model": os.environ.get("HETUNE_MODEL", "gpt-6.1-sol"),
        }
    raise ValueError("unknown provider: %s" % name)


def providers():
    """主模型 + 备用模型（用于超时/报错时的降级重试）。"""
    chain = [p.strip() for p in os.environ.get("PROVIDER_CHAIN", _primary + ",hetune").split(",") if p.strip()]
    out = []
    for name in chain:
        p = _provider(name)
        if p["api_key"]:
            out.append(p)
    if not out:
        raise RuntimeError("未配置任何可用模型，请检查 .env 中的 *_API_KEY")
    return out


def fast_providers():
    """规划/复核角色使用的快模型：默认 deepseek-flash，降低多智能体开销。"""
    fast = os.environ.get("FAST_MODEL", "deepseek-flash").strip()
    chain = [p.strip() for p in os.environ.get("PROVIDER_CHAIN", _primary + ",hetune").split(",") if p.strip()]
    out = []
    for name in chain:
        p = _provider(name)
        if p["api_key"]:
            if name == "deepseek" and fast:
                p = dict(p)
                p["model"] = fast
            out.append(p)
    return out


def db_path():
    return os.environ.get("DATAPILOT_DB", DB_PATH)


MAX_STEPS = int(os.environ.get("MAX_STEPS", "12"))