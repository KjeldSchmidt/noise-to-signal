# news_chat

Sync-invoked Lambda for grounded news Q&A (brief + story thread).

## Flow (LangGraph)

```
START → classify → refuse → END
                 ↘ agent ↔ tools → finalize → END
```

1. Validate `ChatWorkerRequest` (`chunks` + message + history + `user_id`).
2. **classify** — Nova Micro structured scope check (`allowed` + reason).
3. On deny: **refuse** with canned copy.
4. On allow: **agent** ↔ **tools** (`ToolNode` / `search_articles`, max 2 rounds) then **finalize** (structured reply + citations).
5. Langfuse-traced when `langfuse_tracing` is enabled (tag `news_chat`).

Web owns AuthZ + rate limits + baseline scope retrieval; this worker runs the graph.

## Layout

| Module | Role |
|--------|------|
| `state.py` | `ChatState` |
| `graph.py` | Compiled `chat_graph` |
| `schemas.py` | Classifier / answer structured schemas |
| `tools.py` | `search_articles` (`InjectedState` + `Command`) |
| `chat.py` | `run_chat` — invoke graph, map to `ChatWorkerResponse` |
| `main.py` | Lambda handler |
