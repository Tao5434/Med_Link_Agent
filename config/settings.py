"""全局配置模块。

统一从环境变量 / .env 读取运行参数，供各层（DAO、RAG、Agent、Service）共享。
所有配置项都提供默认值，保证「无 API Key、无大模型、无 MySQL」时系统仍可降级运行。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")


def _env(key: str, default: str = "") -> str:
    value = os.getenv(key)
    return default if value is None or value == "" else value


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(key: str, default: bool = False) -> bool:
    raw = _env(key, "true" if default else "false").strip().lower()
    return raw in ("1", "true", "yes", "on", "y")


def _env_float(key: str, default: float) -> float:
    try:
        return float(_env(key, str(default)))
    except (TypeError, ValueError):
        return default


class Settings:
    """应用配置（单例使用）。"""

    # ---------------- 应用 ----------------
    APP_NAME = "诊小通 Agent"
    APP_VERSION = "v2.1.0"
    HOST = _env("APP_HOST", "0.0.0.0")
    PORT = _env_int("APP_PORT", 8012)

    # ---------------- 目录 ----------------
    BASE_DIR = BASE_DIR
    DATA_DIR = BASE_DIR / "data"
    KNOWLEDGE_BASE_DIR = DATA_DIR / "knowledge_base"
    VECTOR_DB_DIR = DATA_DIR / "med_db"
    UPLOAD_DIR = DATA_DIR / "uploads"

    # ---------------- 报告上传 ----------------
    UPLOAD_MAX_MB = _env_int("UPLOAD_MAX_MB", 10)
    UPLOAD_ALLOWED_EXT = [
        e.strip().lower()
        for e in _env("UPLOAD_ALLOWED_EXT", "pdf,txt,csv,md,png,jpg,jpeg,webp,docx,xlsx").split(",")
        if e.strip()
    ]

    # ---------------- 数据库 ----------------
    # 只使用 MySQL。早期版本的 auto 模式会在连不上 MySQL 时静默降级 SQLite，
    # 结果数据实际没有写进数据库，这里已彻底移除该行为。
    DB_BACKEND = _env("DB_BACKEND", "mysql").lower()
    SQLITE_PATH = BASE_DIR / _env("SQLITE_PATH", "data/med_link_agent.db")

    MYSQL_HOST = _env("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT = _env_int("MYSQL_PORT", 3306)
    MYSQL_USER = _env("MYSQL_USER", "root")
    MYSQL_PASSWORD = _env("MYSQL_PASSWORD", "root")
    MYSQL_DATABASE = _env("MYSQL_DATABASE", "med_link_agent")

    # ---------------- 大模型（OpenAI 兼容协议） ----------------
    ENABLE_LLM = _env_bool("ENABLE_LLM", True)
    LLM_BASE_URL = _env("LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    LLM_API_KEY = _env("LLM_API_KEY", "ollama")
    LLM_MODEL = _env("LLM_MODEL", _env("OLLAMA_CHAT_MODEL", "qwen2.5:7b"))
    LLM_TEMPERATURE = _env_float("LLM_TEMPERATURE", 0.3)
    LLM_MAX_TOKENS = _env_int("LLM_MAX_TOKENS", 1024)
    LLM_TIMEOUT = _env_int("LLM_TIMEOUT", 120)
    LLM_MAX_RETRIES = _env_int("LLM_MAX_RETRIES", 3)
    LLM_RETRY_BACKOFF = _env_float("LLM_RETRY_BACKOFF", 0.8)

    # 兼容旧配置项
    OLLAMA_CHAT_MODEL = _env("OLLAMA_CHAT_MODEL", "qwen2.5:7b")
    OLLAMA_EMBEDDING_MODEL = _env("OLLAMA_EMBEDDING_MODEL", "bge-m3")

    # ---------------- RAG ----------------
    # lightweight: 关键词倒排 + 余弦相似度（离线可用）；chroma: 向量库
    RAG_BACKEND = _env("RAG_BACKEND", "lightweight").lower()
    RAG_TOP_K = _env_int("RAG_TOP_K", 5)
    RAG_CHAIN_TOP_K = _env_int("RAG_CHAIN_TOP_K", 6)
    RAG_CHUNK_SIZE = _env_int("RAG_CHUNK_SIZE", 420)
    RAG_CHUNK_OVERLAP = _env_int("RAG_CHUNK_OVERLAP", 60)
    EVIDENCE_MAX = _env_int("EVIDENCE_MAX", 8)

    # ---------------- 联网增强 ----------------
    DEEP_SEARCH_ENABLED = _env_bool("DEEP_SEARCH_ENABLED", False)
    DEEP_SEARCH_TOP_K = _env_int("DEEP_SEARCH_TOP_K", 3)
    DEEP_SEARCH_TIMEOUT = _env_int("DEEP_SEARCH_TIMEOUT", 8)
    # 搜索引引擎优先级；bing = cn.bing.com（境内可直连），duckduckgo 为备用
    DEEP_SEARCH_ENGINES = [
        e.strip() for e in _env("DEEP_SEARCH_ENGINES", "bing,duckduckgo").split(",") if e.strip()
    ]

    # ---------------- 会话与记忆 ----------------
    HISTORY_MEMORY_LIMIT = _env_int("HISTORY_MEMORY_LIMIT", 12)
    HISTORY_MESSAGES_LIMIT = _env_int("HISTORY_MESSAGES_LIMIT", 100)
    DEFAULT_MESSAGES_LIMIT = _env_int("DEFAULT_MESSAGES_LIMIT", 20)
    SESSION_TITLE_LENGTH = _env_int("SESSION_TITLE_LENGTH", 30)

    # ---------------- 业务 ----------------
    DEFAULT_USER_ID = _env("DEFAULT_USER_ID", "guest")
    RECORD_DEFAULT_DAYS = _env_int("RECORD_DEFAULT_DAYS", 7)
    APPOINTMENT_SCHEDULE_DAYS = _env_int("APPOINTMENT_SCHEDULE_DAYS", 7)

    # ---------------- 登录鉴权 ----------------
    # 令牌有效期（小时），令牌保存在 user_tokens 表中
    AUTH_TOKEN_EXPIRE_HOURS = _env_int("AUTH_TOKEN_EXPIRE_HOURS", 72)
    # 是否强制登录：True 时除健康检查与注册/登录外，其余接口都要求 Bearer 令牌
    AUTH_REQUIRED = _env_bool("AUTH_REQUIRED", True)

    DISCLAIMER = "以上内容仅用于健康科普和就医参考，不能替代医生诊断、处方或治疗。"

    # 核心科室列表（仅作数据库不可用时的兜底；实际以 departments 表为准）
    DEPARTMENTS = [
        "消化科", "妇产科", "皮肤科", "内分泌科", "神经内科", "骨科", "外科", "内科",
        "男科", "生殖医学科", "眼科", "肾脏病中心", "泌尿外科", "呼吸科", "药学门诊",
        "急诊科",
    ]

    # 风险等级（附录 B）
    RISK_LEVELS = ["低风险", "中风险", "高风险"]

    @classmethod
    def llm_enabled(cls) -> bool:
        """需求 FR-SETTINGS：llm_enabled = enable_llm 为真 且 api_key 非空。"""
        return bool(cls.ENABLE_LLM and cls.LLM_API_KEY)

    @classmethod
    def api_key_configured(cls) -> bool:
        return bool(cls.LLM_API_KEY)


settings = Settings()
