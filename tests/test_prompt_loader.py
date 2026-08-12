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
    assert catalog.language_additions == {}


def test_build_prompt_selects_language_addition() -> None:
    catalog = _MODULE.load_prompt_catalog(PROMPTS_PATH)

    english = _MODULE.build_prompt(catalog, "en-US")
    russian = _MODULE.build_prompt(catalog, "ru-RU")
    german = _MODULE.build_prompt(catalog, "de-DE")

    assert english.startswith("<reminder_tools_policy>")
    assert english.endswith("</reminder_tools_policy>")
    assert "user's language" in english
    assert "user's language" in russian
    assert english == russian == german == catalog.base


def test_prompt_forbids_model_timestamp_calculation() -> None:
    catalog = _MODULE.load_prompt_catalog(PROMPTS_PATH)

    assert "Never calculate or send `due_at`" in catalog.base
    assert "Home Assistant resolves `when`" in catalog.base
    assert "native timers" in catalog.base


def test_prompt_keeps_the_runtime_policy_concise() -> None:
    catalog = _MODULE.load_prompt_catalog(PROMPTS_PATH)

    assert len(catalog.base.split()) < 100
    assert '"kind":"relative"' not in catalog.base
    assert '"kind":"calendar"' not in catalog.base
    assert "day_of_month" not in catalog.base
    assert "month_day" not in catalog.base
    assert "target_time" not in catalog.base


def test_prompt_distinguishes_create_and_update_fields() -> None:
    catalog = _MODULE.load_prompt_catalog(PROMPTS_PATH)

    assert "Call `create_reminder` with message" in catalog.base
    assert "`update_reminder`" in catalog.base
    assert "changed fields only" in catalog.base


def test_prompt_preserves_tool_outcome_and_confirmation_policy() -> None:
    catalog = _MODULE.load_prompt_catalog(PROMPTS_PATH)

    assert "update/cancellation has multiple matches" in catalog.base
    assert "never" in catalog.base and "claim success" in catalog.base
    assert "briefly confirm" in catalog.base
    assert "clarification ending with `?`" in catalog.base


def test_prompt_loader_rejects_text_outside_policy_block(tmp_path: Path) -> None:
    prompts_dir = tmp_path / "prompts"
    language_dir = prompts_dir / "languages"
    language_dir.mkdir(parents=True)
    (prompts_dir / "base.txt").write_text(
        "outside\n<reminder_tools_policy>rules</reminder_tools_policy>",
        encoding="utf-8",
    )

    try:
        _MODULE.load_prompt_catalog(prompts_dir)
    except ValueError as err:
        assert "only the policy block" in str(err)
    else:
        raise AssertionError("Expected malformed policy prompt to be rejected")
