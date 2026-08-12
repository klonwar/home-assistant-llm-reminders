# Prompt and LLM API contract

## What the model receives

The model does not receive Python implementation details, class docstrings,
`manager.py`, or this documentation. Through Home Assistant's LLM API it
receives:

1. the tool name;
2. the tool description;
3. the serialized parameter schema;
4. the optional prompt fragment returned in `LLMTools.prompt`.

The conversation agent adapts these values to the selected provider. Tool
calls are validated against the schema before the integration receives them.

## Responsibility split

| Concern | Runtime location |
| --- | --- |
| Tool purpose and call timing | `Tool.description` |
| Field names, types, enums, basic requiredness | `Tool.parameters` |
| Universal behavior rules | `prompts/base.txt` |
| Kind-specific field combinations | Integration semantic validation |
| Current time and timezone | Home Assistant resolver |
| Final `due_at` and scheduling | Manager/storage layer |
| Full examples and design rationale | `docs/` and tests |

The schema is the machine-readable contract. Descriptions may be attached to
schema fields when supported by the adapter, but critical rules must not rely
on field descriptions alone. The short base policy and tool description carry
the non-negotiable prohibition on model-generated timestamps.

## Tool description

`create_reminder` should communicate only its purpose and the key invariant:

```text
Create a one-time reminder. Put the user's time intent in when as a relative
interval or calendar expression. Do not calculate an absolute timestamp.
```

`update_reminder` uses the same `when` contract when its time is changed, but
accepts a changed `message`, a changed `when`, or both. List and cancel
descriptions remain focused on their own operations and do not repeat time
rules.

## `when` shape

Use one `when` object with a `kind` discriminator:

```json
{"kind":"relative","duration":[{"value":"5","unit":"minute"}]}
```

```json
{"kind":"calendar","date_ref":"day_of_month","day_of_month":"15","month_ref":"nearest_future","local_time":"13:00"}
```

Keep the shape flat and avoid requiring top-level `oneOf`/`anyOf` constructs.
This is more portable across provider adapters. The integration checks that
relative-only and calendar-only fields are used with the matching `kind`.

## Provider independence

The design does not depend on a provider exposing the current date, current
time, or timezone. Relative requests contain an interval; calendar requests
contain semantic references such as `tomorrow`, `weekday`, or
`day_of_month`. Home Assistant resolves those references after the tool call.

After implementation, inspect Assist traces for each supported provider to
verify that the tool name, schema, and `when` payload are actually exposed.
Do not assume that every adapter preserves optional field descriptions in the
same way.

## Non-goals

- native Home Assistant timer calls;
- model-generated RFC3339 or epoch timestamps;
- provider-specific system-prompt fragments;
- natural-language parsing duplicated inside the integration;
- recurring reminders.

## Decision log

1. **Use schema and descriptions as the API documentation for the model.**
   Repeating the full contract in `base.txt` wastes system-prompt tokens.
2. **Keep one create tool.** Separate relative/calendar tools would reduce
   each schema but increase tool selection and update complexity.
3. **Prefer a flat discriminator.** It avoids provider incompatibilities with
   complex JSON Schema while retaining a single stable public contract.
4. **Validate twice.** Schema validation handles structure; semantic
   validation prevents invalid combinations and unsafe date resolution.
