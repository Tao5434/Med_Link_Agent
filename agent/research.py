"""联网增强 ResearchAgent（需求 FR-DEEPSEARCH）。

在开启联网时检索公开医学资料，与本地证据合并。

**引擎选择**：默认使用 ``cn.bing.com``（国内可直连），失败再回退 DuckDuckGo。
早期版本只用了 DuckDuckGo 的两个入口，而 DuckDuckGo 在境内网络不可达
（连接超时），导致联网功能实际永远处于降级状态。

任何失败（无网络、超时、解析失败）都返回一条**降级证据**，
提示「将基于本地知识库与安全规则回答」，保证主链路不中断。
"""
from __future__ import annotations

import base64
import html
import logging
import re
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import quote_plus, unquote

import requests

from config.settings import settings
from utils.text import truncate

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

FALLBACK_TEXT = "联网检索当前不可用，将基于本地知识库与安全规则回答。"

TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(text: str) -> str:
    return html.unescape(TAG_RE.sub("", text or "")).strip()


# ----------------------------------------------------------------------
# Bing（cn.bing.com / www.bing.com）—— 默认引擎，境内可直连
# ----------------------------------------------------------------------
BING_BLOCK_RE = re.compile(r'<li class="b_algo".*?(?=<li class="b_algo"|</ol>)', re.S)
BING_TITLE_RE = re.compile(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
BING_SNIPPET_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.S)


def _parse_bing(page: str, top_k: int) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for block in BING_BLOCK_RE.finditer(page):
        body = block.group(0)
        m_title = BING_TITLE_RE.search(body)
        if not m_title:
            continue
        title = _strip_tags(m_title.group(2))
        if not title:
            continue
        m_snippet = BING_SNIPPET_RE.search(body)
        snippet = _strip_tags(m_snippet.group(1)) if m_snippet else ""
        items.append(
            _make_item(_clean_url(m_title.group(1)), title, snippet or title, len(items))
        )
        if len(items) >= top_k:
            break
    return items


# ----------------------------------------------------------------------
# DuckDuckGo —— 备用引擎（境内通常不可达，境外可用）
# ----------------------------------------------------------------------
DDG_RESULT_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
    r'class="result__snippet"[^>]*>(.*?)</a>',
    re.S,
)
DDG_LITE_RE = re.compile(r'<a[^>]+class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)


def _parse_duckduckgo(page: str, top_k: int) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for m in DDG_RESULT_RE.finditer(page):
        title = _strip_tags(m.group(2))
        if not title:
            continue
        items.append(
            _make_item(_clean_url(m.group(1)), title, _strip_tags(m.group(3)) or title, len(items))
        )
        if len(items) >= top_k:
            return items

    if not items:
        for m in DDG_LITE_RE.finditer(page):
            title = _strip_tags(m.group(2))
            if not title:
                continue
            items.append(_make_item(_clean_url(m.group(1)), title, title, len(items)))
            if len(items) >= top_k:
                break
    return items


# ----------------------------------------------------------------------
# 引擎注册表
# ----------------------------------------------------------------------
ENGINES: Dict[str, Dict[str, Any]] = {
    "bing": {
        "url": "https://cn.bing.com/search?q={query}",
        "parser": _parse_bing,
        "label": "Bing 中国",
    },
    "bing_intl": {
        "url": "https://www.bing.com/search?q={query}&setmkt=zh-CN",
        "parser": _parse_bing,
        "label": "Bing 国际",
    },
    "duckduckgo": {
        "url": "https://html.duckduckgo.com/html/?q={query}",
        "parser": _parse_duckduckgo,
        "label": "DuckDuckGo",
    },
}

DEFAULT_ENGINE_ORDER = ["bing", "duckduckgo"]


def _engine_order() -> List[str]:
    configured = getattr(settings, "DEEP_SEARCH_ENGINES", None) or DEFAULT_ENGINE_ORDER
    order = [name.strip() for name in configured if name.strip() in ENGINES]
    return order or DEFAULT_ENGINE_ORDER


def _make_item(url: str, title: str, content: str, index: int) -> Dict[str, Any]:
    return {
        "source": url or "web",
        "title": truncate(title, 80),
        "score": round(max(0.3, 0.9 - 0.1 * index), 4),
        "content": truncate(content, 300),
        "kind": "web",
    }


# ----------------------------------------------------------------------
# 主入口
# ----------------------------------------------------------------------
def deep_search(query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
    """执行联网检索，返回证据字典列表；全部引擎失败时返回降级证据。"""
    top_k = top_k or settings.DEEP_SEARCH_TOP_K
    query = (query or "").strip()
    if not query:
        return [_fallback_evidence("查询内容为空")]

    tried: List[str] = []
    for name in _engine_order():
        engine = ENGINES[name]
        url = engine["url"].format(query=quote_plus(query[:120]))
        tried.append(engine["label"])
        try:
            resp = requests.get(url, headers=HEADERS, timeout=settings.DEEP_SEARCH_TIMEOUT)
            if resp.status_code != 200:
                logger.info("联网检索 %s 返回 HTTP %s", name, resp.status_code)
                continue
            resp.encoding = resp.apparent_encoding or "utf-8"
            items = engine["parser"](resp.text, top_k)
            if items:
                logger.info("联网检索命中：%s（%d 条）", name, len(items))
                return items
            logger.info("联网检索 %s 未解析到结果", name)
        except Exception as exc:  # noqa: BLE001 - 联网失败必须降级而非抛出
            logger.info("联网检索 %s 失败：%s", name, exc)

    return [_fallback_evidence("、".join(tried))]


def _clean_url(href: str) -> str:
    """还原真实链接：处理 DuckDuckGo 的 uddg 参数与 Bing 的 /ck/a 跳转。"""
    href = html.unescape(href or "")
    if not href:
        return "web"

    m = re.search(r"uddg=([^&]+)", href)
    if m:
        return unquote(m.group(1))[:200]

    # Bing 跳转：/ck/a?...&u=a1<base64url>
    m = re.search(r"[?&]u=a1([A-Za-z0-9_\-]+)", href)
    if m:
        raw = m.group(1).replace("-", "+").replace("_", "/")
        raw += "=" * (-len(raw) % 4)
        try:
            decoded = base64.b64decode(raw).decode("utf-8", "replace")
            if decoded.startswith("http"):
                return decoded[:200]
        except Exception:  # noqa: BLE001
            pass

    if href.startswith("/"):
        return f"https://cn.bing.com{href}"[:200]
    return href[:200]


def _fallback_evidence(tried: str = "") -> Dict[str, Any]:
    """需求 3.10：仍失败则返回一条降级证据。"""
    content = FALLBACK_TEXT
    if tried:
        content += f"（已尝试：{tried}）"
    return {
        "source": "deep_search_unavailable",
        "title": "联网检索降级提示",
        "score": 0.0,
        "content": content,
        "kind": "fallback",
    }


def engine_status() -> Dict[str, Any]:
    """供 /api/settings 展示当前联网引擎配置。"""
    return {
        "enabled": settings.DEEP_SEARCH_ENABLED,
        "order": _engine_order(),
        "labels": [ENGINES[n]["label"] for n in _engine_order()],
        "top_k": settings.DEEP_SEARCH_TOP_K,
        "timeout": settings.DEEP_SEARCH_TIMEOUT,
    }


# 供测试或扩展使用
_ = Callable
