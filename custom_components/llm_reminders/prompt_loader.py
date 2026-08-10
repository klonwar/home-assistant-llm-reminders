from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_POLICY_OPENING_TAG = "<reminder_tools_policy>"
_POLICY_CLOSING_TAG = "</reminder_tools_policy>"


@dataclass(frozen=True)
class PromptCatalog:
    """Loaded base prompt and language-specific prompt additions."""

    base: str
    language_additions: dict[str, str]


def normalize_language(language: str | None) -> str | None:
    """Return the base language code from a BCP 47-like language tag."""
    if not language:
        return None

    normalized = language.replace("_", "-").strip().casefold()
    if not normalized:
        return None
    return normalized.split("-", 1)[0]


def load_prompt_catalog(prompts_dir: Path | None = None) -> PromptCatalog:
    """Load the base prompt and language additions from bundled text files."""
    prompts_dir = prompts_dir or Path(__file__).with_name("prompts")
    base_path = prompts_dir / "base.txt"
    base = base_path.read_text(encoding="utf-8").strip()
    if not base:
        raise ValueError(f"The base LLM prompt is empty: {base_path}")
    _validate_policy_block(base, base_path)

    language_dir = prompts_dir / "languages"
    language_additions: dict[str, str] = {}
    if language_dir.is_dir():
        for path in sorted(language_dir.glob("*.txt")):
            language = normalize_language(path.stem)
            if language is None:
                continue
            addition = path.read_text(encoding="utf-8").strip()
            if _POLICY_OPENING_TAG in addition or _POLICY_CLOSING_TAG in addition:
                raise ValueError(
                    f"Language prompt must not contain policy XML tags: {path}"
                )
            language_additions[language] = addition

    return PromptCatalog(
        base=base,
        language_additions=language_additions,
    )


def build_prompt(catalog: PromptCatalog, language: str | None) -> str:
    """Insert the matching language addition inside the policy block."""
    _validate_policy_block(catalog.base, "base prompt")
    language_key = normalize_language(language)
    if language_key and (addition := catalog.language_additions.get(language_key)):
        closing_index = catalog.base.index(_POLICY_CLOSING_TAG)
        return (
            f"{catalog.base[:closing_index].rstrip()}\n\n"
            f"{addition}\n{catalog.base[closing_index:]}"
        )
    return catalog.base


def _validate_policy_block(prompt: str, source: Path | str) -> None:
    """Ensure the prompt consists of exactly one complete policy block."""
    if prompt.count(_POLICY_OPENING_TAG) != 1:
        raise ValueError(
            f"Prompt must contain exactly one {_POLICY_OPENING_TAG}: {source}"
        )
    if prompt.count(_POLICY_CLOSING_TAG) != 1:
        raise ValueError(
            f"Prompt must contain exactly one {_POLICY_CLOSING_TAG}: {source}"
        )

    opening_index = prompt.index(_POLICY_OPENING_TAG)
    closing_index = prompt.index(_POLICY_CLOSING_TAG)
    closing_end = closing_index + len(_POLICY_CLOSING_TAG)
    if (
        opening_index > closing_index
        or prompt[:opening_index].strip()
        or prompt[closing_end:].strip()
    ):
        raise ValueError(f"Prompt must contain only the policy block: {source}")
