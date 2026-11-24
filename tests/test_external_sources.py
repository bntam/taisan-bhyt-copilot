"""
Unit Tests for External Sources & Pluggable MCP Registry
Validates:
1. Load default sources (LangCare MCP, Clinic Inventory API, MoH Feed)
2. Add custom external source
3. Toggle source status
4. Delete source
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mcp_server.external_sources import (
    load_sources,
    add_or_update_source,
    toggle_source,
    delete_source,
    get_active_external_contexts
)

class TestExternalSources(unittest.TestCase):

    def test_01_load_default_sources(self):
        sources = load_sources()
        self.assertGreaterEqual(len(sources), 3)
        ids = [s["id"] for s in sources]
        self.assertIn("langcare-mcp", ids)
        self.assertIn("clinic-inventory-api", ids)

    def test_02_add_and_toggle_source(self):
        test_src = {
            "id": "test-telehealth-mcp",
            "name": "Test Telehealth MCP",
            "type": "mcp_client",
            "endpoint": "http://127.0.0.1:9999/mcp",
            "enabled": True,
            "description": "Test integration"
        }
        res = add_or_update_source(test_src)
        self.assertEqual(res["id"], "test-telehealth-mcp")

        toggled = toggle_source("test-telehealth-mcp", False)
        self.assertIsNotNone(toggled)
        if toggled:
            self.assertFalse(toggled["enabled"])

        deleted = delete_source("test-telehealth-mcp")
        self.assertTrue(deleted)

if __name__ == "__main__":
    unittest.main()
