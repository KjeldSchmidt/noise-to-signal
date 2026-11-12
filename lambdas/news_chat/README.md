# news_chat

Sync-invoked Lambda for grounded news Q&A (brief + story thread).

## Flow

1. Validate `ChatWorkerRequest` (chunks + message + history).
2. Nova Micro structured scope check (`allowed` + `ok` / `off_topic` / `injection`).
3. On allow: Nova Lite answer with article text in `<<<DATA>>>` delimiters (untrusted).
4. LangSmith agent id: `news-chat`.

Web owns AuthZ + rate limits + retrieval; this worker only classifies and answers.
