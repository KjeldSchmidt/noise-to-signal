# story_summarizer

Async Event-invoked worker that writes **non-personal** multilingual AI digests on
`StoryThread` (`StoryThreadLocalization` for `en` / `fr` / `de`, plus English mirrors on
`summary` / `label` and `summarized_at`). Triggered from article upsert after a new
thread join when localizations are missing or older than six hours.

Uses LangChain Bedrock Converse (`with_structured_output`) + internal API
context/update endpoints. One call returns native copy for all three product languages
(not translate-from-English).

**Fallback (display):** preferred content languages → `en` → any localization → thread
English mirrors / lead article title.
