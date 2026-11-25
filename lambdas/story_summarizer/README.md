# story_summarizer

Async Event-invoked worker that writes a **non-personal** AI digest on `StoryThread`
(`summary` / `summarized_at`). Triggered from article upsert after a new thread join
when the last summary is missing or older than six hours.

Uses LangChain Bedrock Converse + internal API context/update endpoints.
