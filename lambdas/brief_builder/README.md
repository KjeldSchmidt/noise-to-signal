# brief_builder

Async LangGraph worker that builds a personalized `UserBrief` using AgentCore preferences and Stories-scored candidates from the web internal API.

Actions (`BriefBuilderRequest`):

- `build` — fetch prefs + context → evaluate → `complete_brief`
- `record_preference` — write a preference event to AgentCore Memory
- `erase_preferences` — delete LTM records for `actorId` (privacy)
