"""大模型客户端（需求 2.4：OpenAI 兼容协议，base_url 与 api_key 可配置）。

设计原则：
* 默认不强制依赖真实大模型——未安装 ``openai``、未配置 Key 或服务不可达时，
  ``available`` 为 False，上层自动走规则 + RAG 降级链路；
* 支持重试（需求 3.8：max_retries 1~3 次，退避 0.8s 递增）。
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from config.settings import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """OpenAI 兼容协议聊天客户端。"""

    def __init__(self) -> None:
        self.base_url = settings.LLM_BASE_URL
        self.api_key = settings.LLM_API_KEY
        self.model = settings.LLM_MODEL
        self.enabled = settings.ENABLE_LLM
        self.max_retries = max(1, min(settings.LLM_MAX_RETRIES, 3))
        self.backoff = settings.LLM_RETRY_BACKOFF
        self._client = None
        self._init_error: Optional[str] = None
        self._probe_done = False
        self._probe_ok = False
        self.last_error: Optional[str] = None
        self._build()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        if not self.enabled:
            self._init_error = "ENABLE_LLM=False，已关闭大模型"
            return
        if not self.api_key:
            self._init_error = "未配置 LLM_API_KEY"
            return
        try:
            from openai import OpenAI

            self._client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=settings.LLM_TIMEOUT,
                max_retries=0,
            )
        except Exception as exc:  # noqa: BLE001
            self._init_error = f"{type(exc).__name__}: {exc}"
            self._client = None

    # ------------------------------------------------------------------
    @property
    def available(self) -> bool:
        """是否具备真实大模型能力（配置层面）。"""
        return self._client is not None and settings.llm_enabled()

    def probe(self) -> bool:
        """探测模型服务是否真实可达（结果缓存，避免每次请求都探测）。"""
        if not self.available:
            return False
        if not self._probe_done:
            self._probe_done = True
            try:
                self._client.models.list()
                self._probe_ok = True
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"{type(exc).__name__}: {exc}"
                self._probe_ok = False
        return self._probe_ok

    def reset_probe(self) -> None:
        self._probe_done = False
        self._probe_ok = False

    # ------------------------------------------------------------------
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Optional[str]:
        """调用大模型；失败返回 None（由上层降级处理）。"""
        if not self.available:
            self.last_error = self._init_error or "大模型不可用"
            return None

        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=settings.LLM_TEMPERATURE if temperature is None else temperature,
                    max_tokens=settings.LLM_MAX_TOKENS if max_tokens is None else max_tokens,
                )
                content = (response.choices[0].message.content or "").strip()
                if content:
                    return content
                last_exc = RuntimeError("模型返回空内容")
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning("LLM 调用失败(第 %s 次): %s", attempt + 1, exc)
            if attempt < self.max_retries - 1:
                time.sleep(self.backoff * (attempt + 1))

        self.last_error = f"{type(last_exc).__name__}: {last_exc}" if last_exc else "未知错误"
        return None

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """调用大模型并解析 JSON；解析失败返回 None。"""
        raw = self.chat(messages, temperature=0.1, max_tokens=max_tokens)
        if not raw:
            return None
        return extract_json(raw)

    # ------------------------------------------------------------------
    def status(self) -> dict:
        return {
            "available": self.available,
            "enabled": self.enabled,
            "model": self.model,
            "base_url": self.base_url,
            "api_key_configured": bool(self.api_key),
            "init_error": self._init_error,
            "last_error": self.last_error,
        }


# ----------------------------------------------------------------------
# JSON 解析工具（需求 3.8：JSON 解析 → 叙事解析 → JSON 修复）
# ----------------------------------------------------------------------
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """从模型输出中稳健地提取 JSON 对象。"""
    if not text:
        return None
    candidates: List[str] = []

    fenced = _FENCE_RE.findall(text)
    candidates.extend(f.strip() for f in fenced)
    candidates.append(text.strip())

    # 截取首个 { 到末个 } 之间的内容
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            repaired = _repair_json(candidate)
            if repaired is not None:
                return repaired
    return None


def _repair_json(text: str) -> Optional[Dict[str, Any]]:
    """常见 JSON 瑕疵修复：单引号、尾随逗号、中文引号、未加引号的键。"""
    fixed = text.strip()
    fixed = fixed.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    fixed = re.sub(r",\s*([}\]])", r"\1", fixed)
    fixed = re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', fixed)
    if "'" in fixed and '"' not in fixed:
        fixed = fixed.replace("'", '"')
    try:
        data = json.loads(fixed)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def parse_narrative(text: str, keys: List[str]) -> Dict[str, Any]:
    """叙事解析：从自由文本中按「键：值」提取字段（需求 3.8 降级第 2 步）。"""
    result: Dict[str, Any] = {}
    if not text:
        return result
    for key in keys:
        pattern = re.compile(rf"{key}\s*[:：]\s*(.+?)(?:\n|$)")
        m = pattern.search(text)
        if m:
            value = m.group(1).strip().strip("。；;,")
            if value:
                result[key] = value
    return result


llm_client = LLMClient()
