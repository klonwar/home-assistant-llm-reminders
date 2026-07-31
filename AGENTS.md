# Repository Guidelines

## Project Structure

- `custom_components/llm_reminders/` contains the Home Assistant integration.
  `__init__.py` handles setup, `manager.py` handles persistence and delivery,
  and `llm.py` exposes LLM tools.
- `custom_components/llm_reminders/prompts/` contains the base prompt and
  language additions under `languages/` (for example, `en.txt` and `ru.txt`).
- `tests/` contains pytest tests, including prompt-loader and package-layout
  checks.
- `README.md`, `DESIGN.md`, and `hacs.json` document usage, architecture, and
  HACS packaging.

## Build, Test, and Development Commands

Run these commands from the repository root:

```powershell
python -m pytest tests
python -m compileall -q custom_components\llm_reminders
```

The first runs the test suite; the second checks Python syntax and bytecode
compilation. There is no standalone local server; runtime validation requires
installing the integration in a Home Assistant instance.

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
impact, include test results, and update `manifest.json` when publishing a
new HACS version. Do not include Home Assistant state, secrets, tokens, or
instance-specific configuration.

## Compatibility and Configuration

The LLM platform API used by `llm.py` requires Home Assistant Core 2026.8.0 or
newer. Native Home Assistant timer tools must remain available. Do not commit
`configuration.yaml`, `.storage/`, credentials, or exported device data.
