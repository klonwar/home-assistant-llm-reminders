# README user-first editorial review (2026-08-06)

## Understanding summary

- Improve the README for everyday Home Assistant users without changing
  integration behavior.
- Lead with spoken reminder examples and explain the result in user-facing
  language.
- Preserve installation, compatibility, configuration, language, prompt,
  delivery, limitations, and development information below the introduction.
- Remove agent/repository artifacts and simplify repetitive or overly internal
  wording.

## Assumptions

- Existing implementation facts remain authoritative, including the Core
  2026.8.0 requirement, satellite selection, retry behavior, and limitations.
- This is a documentation-only change; performance, scale, security, and
  reliability behavior are unchanged.
- Maintainer-only notes may be shortened or removed from the user-facing README
  when they do not help installation or operation.

## Decision log

1. Use a user-first structure with practical spoken examples at the top.
2. Keep technical reference content, but move it after the user-facing flow.
3. Remove repository and household-instance artifacts.
4. Remove stale fixed-date JSON examples and highly internal timing details.
5. Keep factual setup prerequisites, language behavior, persistence, retries,
   limitations, and release workflow guidance.

## Final design

The README opens with a value statement, a `What you can say` section, and a
short `How it works` flow. Installation and compatibility follow, then
configuration, language support, prompt guidance, time interpretation,
persistence, limitations, and development. Wording is concise and
action-oriented while keeping user-relevant facts.
