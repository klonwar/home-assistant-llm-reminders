from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION_DIR = ROOT / "custom_components" / "llm_reminders"


def test_hacs_package_contains_llm_platform_at_integration_root() -> None:
    """Keep the LLM platform in the directory HA scans for platforms."""
    manifest_path = INTEGRATION_DIR / "manifest.json"

    assert manifest_path.is_file()
    assert (INTEGRATION_DIR / "__init__.py").is_file()
    assert (INTEGRATION_DIR / "llm.py").is_file()
    assert not (
        INTEGRATION_DIR / "custom_components" / "llm_reminders" / "llm.py"
    ).exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["domain"] == "llm_reminders"
    assert manifest["version"] == "0.1.4"
