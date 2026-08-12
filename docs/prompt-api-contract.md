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
| Field combinations and date inference | Integration semantic validation |
| Current time and timezone | Home Assistant resolver |
| Final `due_at` and scheduling | Manager/storage layer |
| Full examples and design rationale | `docs/` and tests |

The schema is the machine-readable contract. Descriptions may be attached to
schema fields when supported by the adapter, but critical rules must not rely
on field descriptions alone. The short base policy and tool description carry
the non-negotiable prohibition on model-generated timestamps.

## Tool description

`create_reminder` should communicate the extraction task and the key invariant:

```text
Create a one-time reminder by extracting time fields only. Use duration for
"in 5 minutes", local_time for "at 14:50", and date plus local_time for
"tomorrow at 14:50". Omit date when none was spoken; the server chooses the
nearest future occurrence. Do not send kind, date_ref, or absolute timestamps.
```

`update_reminder` uses the same `when` contract when its time is changed, but
accepts a changed `message`, a changed `when`, or both. List and cancel
descriptions remain focused on their own operations and do not repeat time
rules.

## `when` shape

Use one field-first `when` object. The model does not choose a `kind` or
`date_ref`; the server infers both from the populated fields:

```json
{"duration":[{"value":"5","unit":"minute"}]}
```

```json
{"local_time":"14:50"}
```

```json
{"date":"tomorrow","local_time":"14:50"}
```

Calendar fields are `date`, `weekday`, `day_of_month`, `month`, `local_time`,
`day_period`, `hour`, and `meridiem`. `date` is `today`, `tomorrow`,
`day_after_tomorrow`, or an ISO date. If no date field is present, Home
Assistant selects the nearest future occurrence. The integration rejects
mixed relative/calendar fields and unknown internal fields.

## Provider independence

The design does not depend on a provider exposing the current date, current
time, or timezone. Relative requests contain an interval; calendar requests
contain only literal extracted fields such as `tomorrow`, `weekday`, or
`day_of_month`. Home Assistant infers the date reference and resolves it after
the tool call. The model must not call a date/time tool to fill in an omitted
date.

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
3. **Use field-first extraction instead of a discriminator.** The provider
   only maps user words to obvious fields; the server owns kind and date
   inference.
4. **Validate twice.** Schema validation handles structure; semantic
   validation prevents invalid combinations and unsafe date resolution.
