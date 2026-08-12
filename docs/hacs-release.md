# HACS validation and Release Please automation (2026-08-05)

## Understanding summary

- Prepare this Home Assistant integration repository for HACS publishing
  recommendations.
- Add `.github/workflows/validate.yml` with the official HACS Action for the
  `integration` category and the official Hassfest action.
- Run validation on pushes, pull requests, a daily schedule, and manual
  dispatch.
- Add a separate Release Please workflow triggered by pushes to `main`.
- Use the standard Release PR lifecycle: Release Please opens or updates a PR;
  merging it creates a GitHub Release, a `vX.Y.Z` tag, and `CHANGELOG.md`.
- Keep `custom_components/llm_reminders/manifest.json` synchronized through
  the Release PR.
- Store the fine-grained PAT in the repository Actions secret
  `RELEASE_PLEASE_TOKEN`; contributors use Conventional Commits.

## Assumptions and non-goals

- `main` is the default branch and Release PRs are merged manually.
- HACS default-repository submission is a later process, not part of this
  change.
- Integration runtime behavior, dependencies, and public APIs remain
  unchanged.
- HACS and Hassfest action references follow their official examples.
- The PAT is restricted to this repository with `contents`, `issues`, and
  `pull requests` write permissions and an explicit expiration.
- PAT rotation, accumulated Conventional Commits in the first Release PR, and
  mutable official action refs are accepted operational risks.

## Decision log

1. Use two independent workflows rather than combining validation and release
   permissions in one workflow.
2. Run both HACS validation and Hassfest.
3. Use Release Please's manifest-driven configuration for the single root
   package and omit a component prefix from tags.
4. Configure a JSON `extra-files` updater for
   `custom_components/llm_reminders/manifest.json` at `$.version`.
5. Let Release Please own published version bumps; ordinary feature/fix PRs
   must not manually change the manifest version.
6. Validate required manifest keys and SemVer format without assuming a
   particular release number.
7. Use a fine-grained `RELEASE_PLEASE_TOKEN` and serialize Release Please runs
   with a concurrency group.

## Final design

`validate.yml` is read-only and triggers on pushes, pull requests, a daily
schedule, and `workflow_dispatch`. Its HACS job uses `hacs/action@main` with
`category: integration`; its Hassfest job checks out the repository and uses
`home-assistant/actions/hassfest@master`.

`release-please.yml` triggers only on pushes to `main`, uses
`googleapis/release-please-action@v4`, passes `secrets.RELEASE_PLEASE_TOKEN`,
and declares only the required write permissions. A single concurrency group
prevents overlapping Release PR updates. The workflow does not execute
integration code or publish external packages.

`release-please-config.json` defines one root package with the simple release
strategy, root `CHANGELOG.md`, and the JSON `extra-files` updater. The action
runs in manifest mode, creates ordinary `v<version>` tags, and generates the
GitHub Release when the Release PR is merged.

Validation consists of `python -m pytest tests`,
`python -m compileall -q custom_components\\llm_reminders`, JSON parsing for
the Release Please files, and a GitHub acceptance check covering both
validation jobs and Release PR updates.
