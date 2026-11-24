"""
Universal Bring-Your-Own-Key (BYOK) Multi-Provider LLM Client
Supports ANY user-configured LLM API and model without hardcoding private keys or endpoints:
- OpenAI-compatible APIs (OpenAI, OpenRouter, DeepSeek, Groq, Together, Ollama, vLLM, LM Studio, Custom)
- Google Gemini Native API (generativelanguage.googleapis.com)
- Anthropic Claude Native API (api.anthropic.com)

Security Guarantees:
- Zero hardcoded API keys, tokens, or internal server URLs.
- Never reads personal/external agent config files.
- Never logs or echoes raw API keys in responses or diagnostics.
"""

import os
import json
import socket
import logging
import urllib.request
import urllib.error
from urllib.parse import urlparse
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("bhyt.llm_client")

PROVIDER_PRESETS: Dict[str, Dict[str, str]] = {
    "openai_compat": {
        "label": "OpenAI / OpenAI-Compatible",
        "default_url": "https://api.openai.com/v1",
        "example_model": "gpt-4o-mini",
    },
    "openrouter": {
        "label": "OpenRouter (Multi-Model)",
        "default_url": "https://openrouter.ai/api/v1",
        "example_model": "anthropic/claude-3.5-sonnet",
    },
    "gemini": {
        "label": "Google Gemini Native",
        "default_url": "https://generativelanguage.googleapis.com/v1beta",
        "example_model": "gemini-2.5-flash",
    },
    "anthropic": {
        "label": "Anthropic Claude Native",
        "default_url": "https://api.anthropic.com/v1",
        "example_model": "claude-sonnet-4-20250514",
    },
    "ollama": {
        "label": "Ollama (Local Offline LLM)",
        "default_url": "http://127.0.0.1:11434/v1",
        "example_model": "qwen2.5:14b",
    },
    "deepseek": {
        "label": "DeepSeek API",
        "default_url": "https://api.deepseek.com/v1",
        "example_model": "deepseek-chat",
    },
    "groq": {
        "label": "Groq Cloud",
        "default_url": "https://api.groq.com/openai/v1",
        "example_model": "llama-3.3-70b-versatile",
    },
}


def mask_api_key(api_key: Optional[str]) -> str:
    if not api_key:
        return ""
    k = api_key.strip()
    if len(k) <= 8:
        return "****"
    return f"{k[:4]}...{k[-4:]}"


def resolve_llm_config(user_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Merge user-supplied BYOK config with optional server environment variables.
    User-supplied config ALWAYS takes priority over environment variables.
    """
    uc = user_config or {}
    provider = (uc.get("provider") or os.environ.get("LLM_PROVIDER") or "openai_compat").strip().lower()
    api_url = (uc.get("api_url") or uc.get("base_url") or os.environ.get("LLM_BASE_URL") or "").strip()
    api_key = (uc.get("api_key") or os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
    model = (uc.get("model") or os.environ.get("LLM_MODEL") or "").strip()
    if not api_url and provider in PROVIDER_PRESETS and (api_key or provider == "ollama"):
        api_url = PROVIDER_PRESETS[provider]["default_url"]

    enabled = uc.get("enabled")
    if enabled is None:
        enabled = bool(api_url and model) or (os.environ.get("ENABLE_LIVE_LLM", "0") == "1" and bool(api_url and model))

    return {
        "enabled": bool(enabled),
        "provider": provider,
        "api_url": api_url.rstrip("/"),
        "api_key": api_key,
        "model": model,
    }


def is_endpoint_reachable(url: str, timeout: float = 0.5) -> bool:
    """Fast TCP socket check to prevent blocking when a local endpoint is down."""
    if not url:
        return False
    try:
        p = urlparse(url)
        host = p.hostname
        if not host:
            return False
        port = p.port or (443 if p.scheme == "https" else 80)
        if host in ("127.0.0.1", "localhost", "0.0.0.0"):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            rc = sock.connect_ex((host, port))
            sock.close()
            return rc == 0
        return True
    except Exception:
        return False


def _build_request(
    config: Dict[str, Any],
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 900,
) -> Tuple[str, Dict[str, str], Dict[str, Any], str]:
    """Build provider-specific HTTP URL, headers, and JSON body."""
    provider = config["provider"]
    base_url = config["api_url"].rstrip("/")
    api_key = config["api_key"]
    model = config["model"]

    if provider == "gemini":
        if not base_url:
            base_url = PROVIDER_PRESETS["gemini"]["default_url"]
        # Support native Gemini endpoint (:generateContent) unless user pasted an /openai/ URL
        if "/openai" not in base_url:
            clean_model = model.removeprefix("models/")
            url = f"{base_url}/models/{clean_model}:generateContent"
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["x-goog-api-key"] = api_key
            body = {
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
            }
            return url, headers, body, "gemini"

    if provider == "anthropic":
        if not base_url:
            base_url = PROVIDER_PRESETS["anthropic"]["default_url"]
        url = base_url if base_url.endswith("/messages") else f"{base_url}/messages"
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        if api_key:
            headers["x-api-key"] = api_key
        body = {
            "model": model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        return url, headers, body, "anthropic"

    # Default: OpenAI-compatible (OpenAI, OpenRouter, Ollama, DeepSeek, Groq, vLLM, Custom)
    if base_url.endswith("/chat/completions"):
        url = base_url
    else:
        url = f"{base_url}/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "TaiSanh-BHYT-Copilot/2.0",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    return url, headers, body, "openai_compat"


def _extract_response_text(mode: str, res_json: Dict[str, Any]) -> Optional[str]:
    if mode == "gemini":
        candidates = res_json.get("candidates") or []
        if candidates:
            parts = candidates[0].get("content", {}).get("parts") or []
            texts = [p.get("text", "") for p in parts if p.get("text")]
            if texts:
                return "\n".join(texts).strip()
        return None

    if mode == "anthropic":
        content_blocks = res_json.get("content") or []
        texts = [b.get("text", "") for b in content_blocks if b.get("type") == "text" and b.get("text")]
        if texts:
            return "\n".join(texts).strip()
        return None

    choices = res_json.get("choices") or []
    if choices:
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    return None


def call_universal_llm(
    system_prompt: str,
    user_prompt: str,
    user_config: Optional[Dict[str, Any]] = None,
    timeout: float = 12.0,
) -> Dict[str, Any]:
    """
    Invoke any user-configured LLM API cleanly.
    Returns {"ok": bool, "content": str | None, "model": str, "provider": str, "error": str | None}.
    """
    cfg = resolve_llm_config(user_config)
    if not cfg["enabled"] or not cfg["api_url"] or not cfg["model"]:
        return {
            "ok": False,
            "content": None,
            "model": cfg["model"] or "unconfigured",
            "provider": cfg["provider"],
            "error": "LLM not configured (running in private offline RAG mode).",
        }

    # Local providers like Ollama don't need an API key, cloud providers usually do
    is_local = any(h in cfg["api_url"] for h in ("127.0.0.1", "localhost", "0.0.0.0"))
    if not is_local and not cfg["api_key"] and cfg["provider"] != "ollama":
        return {
            "ok": False,
            "content": None,
            "model": cfg["model"],
            "provider": cfg["provider"],
            "error": "API Key is required for remote LLM provider.",
        }

    if not is_endpoint_reachable(cfg["api_url"], timeout=0.4):
        return {
            "ok": False,
            "content": None,
            "model": cfg["model"],
            "provider": cfg["provider"],
            "error": "Configured local LLM endpoint is unreachable.",
        }

    try:
        url, headers, payload, mode = _build_request(cfg, system_prompt, user_prompt)
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            res_json = json.loads(raw)
            text = _extract_response_text(mode, res_json)
            if text:
                return {
                    "ok": True,
                    "content": text,
                    "model": cfg["model"],
                    "provider": cfg["provider"],
                    "error": None,
                }
            return {
                "ok": False,
                "content": None,
                "model": cfg["model"],
                "provider": cfg["provider"],
                "error": "Empty completion returned by provider.",
            }
    except urllib.error.HTTPError as he:
        err_msg = f"HTTP {he.code}: {he.reason}"
        logger.warning(f"LLM HTTPError ({cfg['provider']}): {err_msg}")
        return {
            "ok": False,
            "content": None,
            "model": cfg["model"],
            "provider": cfg["provider"],
            "error": err_msg,
        }
    except Exception as e:
        logger.warning(f"LLM Error ({cfg['provider']}): {type(e).__name__}")
        return {
            "ok": False,
            "content": None,
            "model": cfg["model"],
            "provider": cfg["provider"],
            "error": str(e),
        }


def list_available_models(user_config: Optional[Dict[str, Any]] = None, timeout: float = 6.0) -> Dict[str, Any]:
    """Fetch available models from user-configured provider without leaking credentials."""
    cfg = resolve_llm_config(user_config)
    provider = cfg["provider"]
    base_url = cfg["api_url"].rstrip("/")
    api_key = cfg["api_key"]

    if provider == "anthropic":
        return {
            "ok": True,
            "provider": provider,
            "models": [
                "claude-sonnet-4-20250514",
                "claude-3-7-sonnet-20250219",
                "claude-3-5-haiku-20241022",
            ],
        }

    if not base_url:
        return {"ok": False, "provider": provider, "models": [], "error": "Missing API Base URL"}

    try:
        if provider == "gemini" and "/openai" not in base_url:
            url = f"{base_url}/models"
            headers = {"x-goog-api-key": api_key} if api_key else {}
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [
                    m.get("name", "").removeprefix("models/")
                    for m in (data.get("models") or [])
                    if "generateContent" in (m.get("supportedGenerationMethods") or [])
                ]
                return {"ok": True, "provider": provider, "models": models[:50]}

        models_url = base_url[:-len("/chat/completions")] + "/models" if base_url.endswith("/chat/completions") else f"{base_url}/models"
        headers = {"User-Agent": "TaiSanh-BHYT-Copilot/2.0"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        req = urllib.request.Request(models_url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("id") for m in (data.get("data") or []) if m.get("id")]
            return {"ok": True, "provider": provider, "models": sorted(models)[:80]}
    except Exception as e:
        return {"ok": False, "provider": provider, "models": [], "error": str(e)}


def test_llm_connection(user_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Perform a minimal 1-token/short verification ping against user's LLM endpoint."""
    cfg = resolve_llm_config(user_config)
    if not cfg["api_url"] or not cfg["model"]:
        return {
            "ok": False,
            "provider": cfg["provider"],
            "model": cfg["model"],
            "error": "Vui lòng nhập đầy đủ API Base URL và Model Name.",
        }
    res = call_universal_llm(
        system_prompt="Reply strictly with: OK",
        user_prompt="Ping",
        user_config={**cfg, "enabled": True},
        timeout=8.0,
    )
    return {
        "ok": res["ok"],
        "provider": cfg["provider"],
        "model": cfg["model"],
        "key_masked": mask_api_key(cfg["api_key"]),
        "reply_preview": (res["content"] or "")[:80] if res["ok"] else "",
        "error": res.get("error"),
    }
