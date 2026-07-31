from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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

    language_dir = prompts_dir / "languages"
    language_additions: dict[str, str] = {}
    if language_dir.is_dir():
        for path in sorted(language_dir.glob("*.txt")):
            language = normalize_language(path.stem)
            if language is None:
                continue
            language_additions[language] = path.read_text(encoding="utf-8").strip()

    return PromptCatalog(
        base=base,
        language_additions=language_additions,
    )


def build_prompt(catalog: PromptCatalog, language: str | None) -> str:
    """Combine the base prompt with the matching language addition."""
    parts = [catalog.base]
    language_key = normalize_language(language)
    if language_key and (addition := catalog.language_additions.get(language_key)):
        parts.append(addition)
    return "\n\n".join(parts)
