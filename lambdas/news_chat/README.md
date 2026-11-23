# news_chat

Sync-invoked Lambda for grounded news Q&A (brief + story thread).

## Flow

1. Validate `ChatWorkerRequest` (chunks + message + history + `user_id`).
2. Nova Micro structured scope check (`allowed` + `ok` / `off_topic` / `injection`).
3. On allow: Nova Lite may call `search_articles` (title + clustering-consistent ANN via Django internal API), then returns a structured reply + citations.
4. LangSmith agent id: `news-chat`.

Web owns AuthZ + rate limits + baseline scope retrieval; this worker classifies, optionally searches, and answers.
