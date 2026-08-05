from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
PROMPT_LOADER_PATH = (
    ROOT / "custom_components" / "llm_reminders" / "prompt_loader.py"
)
PROMPTS_PATH = ROOT / "custom_components" / "llm_reminders" / "prompts"

_SPEC = importlib.util.spec_from_file_location(
    "llm_reminders_prompt_loader", PROMPT_LOADER_PATH
)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def test_language_tags_normalize_to_base_language() -> None:
    assert _MODULE.normalize_language("en-US") == "en"
    assert _MODULE.normalize_language("ru_RU") == "ru"
    assert _MODULE.normalize_language(None) is None


def test_prompt_catalog_contains_base_and_language_additions() -> None:
    catalog = _MODULE.load_prompt_catalog(PROMPTS_PATH)

    assert catalog.base
    assert set(catalog.language_additions) == {"en", "ru"}


def test_build_prompt_selects_language_addition() -> None:
    catalog = _MODULE.load_prompt_catalog(PROMPTS_PATH)

    english = _MODULE.build_prompt(catalog, "en-US")
    russian = _MODULE.build_prompt(catalog, "ru-RU")
    german = _MODULE.build_prompt(catalog, "de-DE")

    assert "For English requests" in english
    assert "Пользователь говорит по-русски" in russian
    assert "Пользователь говорит по-русски" not in english
    assert german == catalog.base


def test_prompt_requires_timezone_offset_for_due_at() -> None:
    catalog = _MODULE.load_prompt_catalog(PROMPTS_PATH)

    assert "must include a" in catalog.base
    assert "timezone offset" in catalog.base
    assert "часовым поясом" in catalog.language_additions["ru"]
