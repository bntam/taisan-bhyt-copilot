"""
Unit Tests for BYOK Multi-Provider LLM Client & Security Safeguards
Validates:
1. Safe credential resolution & masking (zero secret leaks)
2. Provider preset resolution (OpenAI, Gemini, Anthropic, OpenRouter, Ollama)
3. Offline fallback behavior when unconfigured or disabled
4. Connection test harness with mocked responses
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mcp_server.llm_client import (
    resolve_llm_config,
    mask_api_key,
    test_llm_connection,
    call_universal_llm,
    PROVIDER_PRESETS
)
from mcp_server.rag_llm import ask_hybrid_rag_llm

class TestLlmByokClient(unittest.TestCase):

    def test_01_api_key_masking(self):
        self.assertEqual(mask_api_key(""), "")
        self.assertEqual(mask_api_key("1234"), "****")
        self.assertEqual(mask_api_key("sk-proj-1234567890abcdef"), "sk-p...cdef")

    def test_02_resolve_unconfigured_defaults_to_offline(self):
        cfg = resolve_llm_config({})
        self.assertFalse(cfg["enabled"])
        self.assertIn(cfg["provider"], PROVIDER_PRESETS)

    def test_03_resolve_presets_defaults(self):
        # Gemini preset
        cfg_gemini = resolve_llm_config({"provider": "gemini", "api_key": "dummy_key", "model": "gemini-2.5-flash"})
        self.assertTrue(cfg_gemini["enabled"])
        self.assertIn("googleapis.com", cfg_gemini["api_url"])

        # Ollama local preset
        cfg_ollama = resolve_llm_config({"provider": "ollama", "model": "qwen2.5:14b"})
        self.assertIn("11434", cfg_ollama["api_url"])

        # OpenRouter preset
        cfg_or = resolve_llm_config({"provider": "openrouter", "api_key": "sk-or-v1-dummy", "model": "anthropic/claude-3.5-sonnet"})
        self.assertIn("openrouter.ai", cfg_or["api_url"])

    def test_04_call_universal_llm_unconfigured_fails_gracefully(self):
        res = call_universal_llm("system prompt", "user query", user_config={"enabled": False})
        self.assertFalse(res["ok"])
        self.assertIsNone(res["content"])
        self.assertIn("offline RAG", res["error"])

    def test_05_test_connection_without_keys_reports_clean_error(self):
        res = test_llm_connection({"provider": "openai_compat", "api_url": "", "model": ""})
        self.assertFalse(res["ok"])
        self.assertIn("Vui lòng nhập", res["error"])

    def test_06_rag_engine_falls_back_to_local_catalog_when_llm_disabled(self):
        res = ask_hybrid_rag_llm(
            query="Bệnh nhân tăng huyết áp có dùng được Cam thảo không?",
            hospital_level="4",
            use_llm=False
        )
        self.assertEqual(res["mode"], "rag_offline_fallback")
        self.assertIn("Cam Thảo", res["answer"])
        self.assertIn("Glycyrrhizin", res["answer"])
        self.assertIn("references", res)

if __name__ == "__main__":
    unittest.main()
