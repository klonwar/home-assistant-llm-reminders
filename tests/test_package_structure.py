from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION_DIR = ROOT / "custom_components" / "llm_reminders"
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


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
    assert isinstance(manifest["version"], str)
    assert SEMVER_PATTERN.fullmatch(manifest["version"])


def test_release_please_manifest_tracks_integration_version() -> None:
    """Keep Release Please's bootstrap version aligned with the integration."""
    integration_manifest = json.loads(
        (INTEGRATION_DIR / "manifest.json").read_text(encoding="utf-8")
    )
    release_manifest = json.loads(
        (ROOT / ".release-please-manifest.json").read_text(encoding="utf-8")
    )
    release_config = json.loads(
        (ROOT / "release-please-config.json").read_text(encoding="utf-8")
    )

    assert release_manifest["."] == integration_manifest["version"]
    package_config = release_config["packages"]["."]
    assert package_config["changelog-path"] == "CHANGELOG.md"
    assert {
        extra_file["path"]: extra_file["jsonpath"]
        for extra_file in package_config["extra-files"]
    } == {"custom_components/llm_reminders/manifest.json": "$.version"}


def test_beta_release_please_config_uses_prerelease_strategy() -> None:
    """Keep the beta workflow isolated from the stable release strategy."""
    beta_config = json.loads(
        (ROOT / "release-please-config.beta.json").read_text(encoding="utf-8")
    )

    assert beta_config["versioning"] == "prerelease"
    assert beta_config["prerelease-type"] == "beta"
    assert beta_config["prerelease"] is True
    package_config = beta_config["packages"]["."]
    assert package_config["changelog-path"] == "CHANGELOG.md"
    assert {
        extra_file["path"]: extra_file["jsonpath"]
        for extra_file in package_config["extra-files"]
    } == {"custom_components/llm_reminders/manifest.json": "$.version"}


def test_validation_skips_release_please_technical_branches() -> None:
    """Keep generated Release Please branches out of repository validation."""
    workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text(
        encoding="utf-8"
    )

    for branch in (
        "release-please--branches--main",
        "release-please--branches--beta",
    ):
        assert workflow.count(f"github.ref_name == '{branch}'") == 2
        assert workflow.count(f"github.head_ref == '{branch}'") == 2

    assert workflow.count("github.event_name == 'push'") == 2
    assert workflow.count("github.event_name == 'pull_request'") == 2
    assert workflow.count(
        "github.event.pull_request.head.repo.full_name == github.repository"
    ) == 2
    assert workflow.count("${{ !(") == 2


def test_validation_pushes_only_stable_and_beta_branches() -> None:
    """Avoid validation runs for generated branches, feature branches, and tags."""
    workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text(
        encoding="utf-8"
    )

    assert "  push:\n    branches:\n      - main\n      - beta\n" in workflow
    assert "  pull_request:\n" in workflow
    assert "  schedule:\n" in workflow
    assert "  workflow_dispatch:\n" in workflow
