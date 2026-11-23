"""Run brief build / preference side actions."""

from __future__ import annotations

import logging

from n2s_api import BriefBuilderRequest, BriefCompleteRequest
from n2s_preferences import get_preference_client
from n2s_web_client import complete_brief

from graph import brief_graph

logger = logging.getLogger(__name__)


def run_build(req: BriefBuilderRequest) -> None:
    if req.brief_id is None:
        raise ValueError("brief_id is required for build")
    try:
        brief_graph.invoke(
            {
                "user_id": req.user_id,
                "brief_id": req.brief_id,
                "preferences": [],
                "candidates": [],
                "selected": [],
                "error": "",
            }
        )
    except Exception as exc:
        logger.exception("brief build failed user=%s brief=%s", req.user_id, req.brief_id)
        try:
            complete_brief(
                BriefCompleteRequest(
                    brief_id=req.brief_id,
                    user_id=req.user_id,
                    status="failed",
                    error=str(exc)[:2000],
                    items=[],
                )
            )
        except Exception:
            logger.exception("failed to mark brief as failed")


def run_record_preference(req: BriefBuilderRequest) -> None:
    client = get_preference_client()
    if client is None:
        logger.warning("AGENTCORE_MEMORY_ID unset; skipping preference record")
        return
    client.record_preference(req.user_id, req.preference_text)


def run_erase_preferences(req: BriefBuilderRequest) -> int:
    client = get_preference_client()
    if client is None:
        logger.warning("AGENTCORE_MEMORY_ID unset; nothing to erase")
        return 0
    return client.delete_all_for_user(req.user_id)


def run_list_preferences(req: BriefBuilderRequest) -> list[dict[str, str]]:
    client = get_preference_client()
    if client is None:
        logger.warning("AGENTCORE_MEMORY_ID unset; returning empty preference list")
        return []
    return [{"id": r.id, "text": r.text} for r in client.list_preference_records(req.user_id)]


def run_delete_preference(req: BriefBuilderRequest) -> bool:
    client = get_preference_client()
    if client is None:
        logger.warning("AGENTCORE_MEMORY_ID unset; cannot delete preference")
        return False
    return client.delete_preference_record(req.user_id, req.memory_record_id)


def dispatch(req: BriefBuilderRequest) -> dict[str, object]:
    if req.action == "build":
        run_build(req)
        return {"ok": True, "action": "build"}
    if req.action == "record_preference":
        run_record_preference(req)
        return {"ok": True, "action": "record_preference"}
    if req.action == "erase_preferences":
        deleted = run_erase_preferences(req)
        return {"ok": True, "action": "erase_preferences", "deleted": deleted}
    if req.action == "list_preferences":
        memories = run_list_preferences(req)
        return {"ok": True, "action": "list_preferences", "memories": memories}
    if req.action == "delete_preference":
        ok = run_delete_preference(req)
        return {"ok": ok, "action": "delete_preference"}
    raise ValueError(f"unknown action: {req.action}")
