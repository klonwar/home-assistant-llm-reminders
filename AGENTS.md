# Repository Guidelines

## Project Structure

- `custom_components/llm_reminders/` contains the Home Assistant integration.
  `__init__.py` handles setup, `manager.py` handles persistence and delivery,
  and `llm.py` exposes LLM tools.
- `custom_components/llm_reminders/prompts/` contains the base prompt and
  language additions under `languages/` (for example, `en.txt` and `ru.txt`).
- `tests/` contains pytest tests, including prompt-loader and package-layout
  checks.
- `README.md`, `DESIGN.md`, `hacs.json`, `LICENSE`, and `.github/workflows/`
  document usage, architecture, licensing, and HACS/release automation.

## Build, Test, and Development Commands

Run these commands from the repository root:

```powershell
python -m pytest tests
python -m compileall -q custom_components\llm_reminders
```

The first runs the test suite; the second checks Python syntax and bytecode
compilation. There is no standalone local server; runtime validation requires
installing the integration in a Home Assistant instance.

## HACS Publishing

- Keep `hacs.json` in the repository root with `name` and
  `content_in_root: false`.
- Keep `LICENSE` in the repository root. Do not replace or change the license
  in a feature PR without an explicit maintainer decision.
- Keep the integration brand asset at
  `custom_components/llm_reminders/brand/icon.png`. Use a square PNG logo;
  never commit a placeholder, secret, or instance-specific screenshot.
- Maintain these GitHub repository topics: `home-assistant`, `hacs`,
  `home-assistant-integration`, and `custom-component`. Topics are repository
  metadata configured in GitHub Settings, not keys in `hacs.json`.
- Keep `manifest.json` keys Hassfest-sorted: `domain`, `name`, then the
  remaining keys alphabetically. Integrations with `async_setup` must expose
  the appropriate `CONFIG_SCHEMA`; this config-entry-only integration uses
  `cv.config_entry_only_config_schema(DOMAIN)`.
- Keep HACS validation and Hassfest enabled in `.github/workflows/validate.yml`.
  Do not add `ignore` entries merely to hide a failed requirement; fix the
  repository metadata or document an approved exception first.

## Coding Style and Naming

Use Python with four-space indentation, type annotations, `async` APIs for
Home Assistant operations, and module-level `_LOGGER` instances. Keep file and
symbol names descriptive and use `snake_case` for functions and variables.
Avoid blocking filesystem or network I/O in the event loop. Keep prompts in
text files rather than hardcoding them in Python.

## Testing Guidelines

Use pytest. Test files follow `tests/test_<area>.py`; test functions use
`test_<behavior>()`. Add tests for new prompt-selection, persistence, or
validation behavior. The full suite must pass before submission.

## Commits and Pull Requests

Use short imperative prefixes consistent with the history, such as `feat:`,
`fix:`, and `docs:` (for example, `feat: add multilingual reminder prompts`).
Pull requests should describe the behavior change, explain compatibility
impact, include test results, and let Release Please update the integration
version and changelog in the release PR. Do not include Home Assistant state,
secrets, tokens, or instance-specific configuration.

## Versioning

Release Please is the source of truth for published versions. Ordinary
feature and fix pull requests must not manually bump the version in
`custom_components/llm_reminders/manifest.json`; Release Please updates it in
the Release PR together with `CHANGELOG.md`. Keep the manifest version valid
SemVer and verify that it matches `.release-please-manifest.json` during local
checks. Documentation-only changes outside the integration do not require a
release.

## Compatibility and Configuration

The LLM platform API used by `llm.py` requires Home Assistant Core 2026.8.0 or
newer. Native Home Assistant timer tools must remain available. Do not commit
`configuration.yaml`, `.storage/`, credentials, or exported device data.
