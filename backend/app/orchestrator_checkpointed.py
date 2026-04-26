"""Checkpointed debate orchestration that pauses after each round."""

import logging
import threading
import uuid

from app.agents.prompts import detect_decision_category, get_rounds
from app.db.dynamodb import (
    complete_debate_session,
    create_debate_session,
    get_debate_session,
    update_debate_session,
)
from app.grounding import build_grounding_context
from app.orchestrator import (
    TOOL_MAP,
    _assign_personas,
    _generate_structured_timeline,
    _generate_verdict,
    _get_resources,
    _persist_to_agentcore_memory,
    _run_round,
    _stream_single_round,
)
from app.schemas import (
    CheckpointedDebateResponse,
    FinalizationProgress,
    RoundMetrics,
    RoundResult,
)
from app.tools.knowledge import research_insight

logger = logging.getLogger(__name__)


def _deserialize_transcript(items: list[dict] | list[RoundResult]) -> list[RoundResult]:
    return [item if isinstance(item, RoundResult) else RoundResult(**item) for item in items or []]


def _deserialize_metrics(items: list[dict | None] | list[RoundMetrics | None]) -> list[RoundMetrics | None]:
    metrics: list[RoundMetrics | None] = []
    for item in items or []:
        if item is None or isinstance(item, RoundMetrics):
            metrics.append(item)
        else:
            metrics.append(RoundMetrics(**item))
    return metrics


def _serialize_models(items: list) -> list:
    serialized: list = []
    for item in items:
        if item is None:
            serialized.append(None)
        elif hasattr(item, "model_dump"):
            serialized.append(item.model_dump())
        else:
            serialized.append(item)
    return serialized


def _append_round_summary(debate_summary: str, round_number: int, round_name: str, result: RoundResult) -> str:
    if result.status != "completed":
        return debate_summary

    updated = debate_summary
    updated += f"\n[Round {round_number} - {round_name}]\n"
    updated += f"Path A argued: {result.alpha[:400]}...\n"
    updated += f"Path B argued: {result.beta[:400]}...\n"
    return updated


def _session_to_response(debate_id: str, session: dict) -> CheckpointedDebateResponse:
    """Normalize a stored checkpointed session into the API response shape."""
    transcript = _deserialize_transcript(session.get("transcript", []))
    metrics = _deserialize_metrics(session.get("metrics", []))
    total_rounds = int(session.get("total_rounds", len(transcript) or 5))
    current_round_index = int(session.get("current_round_index", len(transcript)))
    status = session.get("status", "paused")

    next_round_number = None
    if status == "paused" and current_round_index < total_rounds:
        next_round_number = current_round_index + 1

    finalization_progress_raw = session.get("finalization_progress")
    finalization_progress: FinalizationProgress | None = None
    if isinstance(finalization_progress_raw, dict):
        try:
            finalization_progress = FinalizationProgress(**finalization_progress_raw)
        except Exception:
            finalization_progress = None

    return CheckpointedDebateResponse(
        status=status,
        debate_id=debate_id,
        transcript=transcript,
        verdict=session.get("verdict", ""),
        timeline=session.get("timeline"),
        metrics=metrics,
        completed_rounds=len([r for r in transcript if r.status == "completed"]),
        total_rounds=total_rounds,
        resources=session.get("resources", []),
        next_round_number=next_round_number,
        finalization_progress=finalization_progress,
    )


def _build_partial_verdict(transcript: list[RoundResult], user_context: dict, total_rounds: int) -> str:
    completed = [r for r in transcript if r.status == "completed"]
    if len(completed) >= 3:
        return _generate_verdict(transcript, user_context)
    if len(completed) >= 1:
        return (
            f"Only {len(completed)} of {total_rounds} rounds completed successfully. "
            "The AI service may be experiencing high demand. "
            "Here's a partial analysis based on the available rounds."
        )
    return "The debate could not be completed. Please try again."


def _finalize_checkpointed_session_bundle(
    debate_id: str,
    transcript: list[RoundResult],
    metrics: list[RoundMetrics | None],
    debate_summary: str,
    prev_beta: str | None,
    user_context: dict,
    total_rounds: int,
    interjections_history: list[str] | None = None,
) -> None:
    """Finish verdict/timeline/resource generation after the final round without blocking SSE."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    interjections_history = list(interjections_history or [])
    user_context = dict(user_context)
    user_context["_interjections"] = list(interjections_history)

    completed_rounds = len([r for r in transcript if r.status == "completed"])
    timeline_active = completed_rounds >= 3

    progress: dict[str, str] = {
        "verdict": "running",
        "timeline": "running" if timeline_active else "skipped",
        "resources": "running",
    }
    update_debate_session(debate_id, {"finalization_progress": dict(progress)})

    results: dict[str, object] = {}
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            verdict_future = pool.submit(_build_partial_verdict, transcript, user_context, total_rounds)
            resources_future = pool.submit(lambda: _serialize_models(_get_resources(user_context)))
            future_to_name = {verdict_future: "verdict", resources_future: "resources"}
            if timeline_active:
                timeline_future = pool.submit(_generate_structured_timeline, transcript, user_context)
                future_to_name[timeline_future] = "timeline"

            for fut in as_completed(future_to_name):
                name = future_to_name[fut]
                results[name] = fut.result()
                progress[name] = "done"
                if len(results) < len(future_to_name):
                    update_debate_session(debate_id, {"finalization_progress": dict(progress)})

        verdict = results.get("verdict", "")
        timeline = results.get("timeline") if timeline_active else None
        resources = results.get("resources", [])
    except Exception:
        logger.exception("Async checkpointed finalization failed for debate_id=%s", debate_id)
        try:
            verdict = _build_partial_verdict(transcript, user_context, total_rounds)
        except Exception:
            verdict = "The verdict could not be fully generated. Please try opening this debate again in a moment."
        timeline = None
        resources = []
        progress = {
            "verdict": "done" if verdict else "running",
            "timeline": "skipped",
            "resources": "done" if resources else "skipped",
        }

    complete_debate_session(
        debate_id,
        {
            "current_round_index": total_rounds,
            "transcript": _serialize_models(transcript),
            "metrics": _serialize_models(metrics),
            "debate_summary": debate_summary,
            "prev_beta": prev_beta,
            "verdict": verdict,
            "timeline": timeline.model_dump() if timeline else None,
            "resources": resources,
            "total_rounds": total_rounds,
            "interjections": list(interjections_history),
            "finalization_progress": dict(progress),
        },
    )
    _persist_to_agentcore_memory(debate_id, user_context, transcript, verdict)


def start_checkpointed_debate(user_context: dict, user_id: str = "anonymous") -> CheckpointedDebateResponse:
    """Run the first round only, then persist paused state."""
    debate_id = str(uuid.uuid4())
    category = detect_decision_category(
        user_context["path_a"],
        user_context["path_b"],
        constraints=user_context.get("constraints"),
        writing_samples=user_context.get("writing_samples"),
        template_id=user_context.get("template_id"),
    )
    rounds = get_rounds(category)
    tools = TOOL_MAP.get(category, [research_insight])
    alpha_persona, beta_persona = _assign_personas(user_context["path_a"], user_context["path_b"])

    enriched_context = {
        **user_context,
        "_category": category,
        "debate_id": debate_id,
        "user_id": user_id,
    }
    build_grounding_context(enriched_context, category)

    result = _run_round(
        rounds[0],
        enriched_context,
        None,
        0,
        [],
        "",
        tools,
        alpha_persona,
        beta_persona,
    )
    transcript = [result]
    metrics: list[RoundMetrics | None] = [result.metrics]
    debate_summary = _append_round_summary("", 1, rounds[0]["name"], result)
    prev_beta = result.beta if result.status == "completed" else None

    create_debate_session(
        debate_id=debate_id,
        user_id=user_id,
        user_input=enriched_context,
        session_data={
            "status": "paused",
            "current_round_index": 1,
            "transcript": _serialize_models(transcript),
            "metrics": _serialize_models(metrics),
            "debate_summary": debate_summary,
            "prev_beta": prev_beta,
            "category": category,
            "alpha_persona_label": alpha_persona["label"],
            "beta_persona_label": beta_persona["label"],
            "total_rounds": len(rounds),
        },
    )

    completed = len([r for r in transcript if r.status == "completed"])
    return CheckpointedDebateResponse(
        status="paused",
        debate_id=debate_id,
        transcript=transcript,
        verdict="",
        metrics=metrics,
        completed_rounds=completed,
        total_rounds=len(rounds),
        resources=[],
        next_round_number=2 if len(rounds) > 1 else None,
    )


def continue_checkpointed_debate(debate_id: str, interjection: str | None = None) -> CheckpointedDebateResponse:
    """Run exactly one additional round for a paused debate session."""
    session = get_debate_session(debate_id)
    if not session:
        raise ValueError("Debate session not found.")

    if session.get("status") == "complete":
        return _session_to_response(debate_id, session)

    if session.get("status") == "finalizing":
        return _session_to_response(debate_id, session)

    user_context = dict(session.get("input", {}) or {})
    category = session.get("category", "general")
    rounds = get_rounds(category)
    tools = TOOL_MAP.get(category, [research_insight])
    alpha_persona, beta_persona = _assign_personas(user_context["path_a"], user_context["path_b"])
    transcript = _deserialize_transcript(session.get("transcript", []))
    metrics = _deserialize_metrics(session.get("metrics", []))
    debate_summary = session.get("debate_summary", "")
    prev_beta = session.get("prev_beta")
    current_round_index = int(session.get("current_round_index", len(transcript)))

    interjections_history: list[str] = list(session.get("interjections", []) or [])
    user_context["_interjections"] = list(interjections_history)

    if interjection:
        debate_summary += f"\n[User interjects]: {interjection}\n"
        interjections_history.append(interjection)
        user_context["_interjections"] = list(interjections_history)

    if current_round_index >= len(rounds):
        raise ValueError("Debate session is already at the final round.")

    round_info = rounds[current_round_index]
    result = _run_round(
        round_info,
        user_context,
        prev_beta,
        current_round_index,
        transcript,
        debate_summary,
        tools,
        alpha_persona,
        beta_persona,
        interjection=interjection,
    )
    transcript.append(result)
    metrics.append(result.metrics)
    debate_summary = _append_round_summary(
        debate_summary,
        current_round_index + 1,
        round_info["name"],
        result,
    )
    if result.status == "completed":
        prev_beta = result.beta

    next_round_index = current_round_index + 1
    completed_rounds = len([r for r in transcript if r.status == "completed"])

    if next_round_index >= len(rounds):
        from concurrent.futures import ThreadPoolExecutor, as_completed

        timeline_active = completed_rounds >= 3
        progress: dict[str, str] = {
            "verdict": "running",
            "timeline": "running" if timeline_active else "skipped",
            "resources": "running",
        }
        update_debate_session(debate_id, {"finalization_progress": dict(progress)})

        results: dict[str, object] = {}
        with ThreadPoolExecutor(max_workers=3) as pool:
            verdict_future = pool.submit(_build_partial_verdict, transcript, user_context, len(rounds))
            resources_future = pool.submit(lambda: _serialize_models(_get_resources(user_context)))
            future_to_name = {verdict_future: "verdict", resources_future: "resources"}
            if timeline_active:
                timeline_future = pool.submit(_generate_structured_timeline, transcript, user_context)
                future_to_name[timeline_future] = "timeline"

            for fut in as_completed(future_to_name):
                name = future_to_name[fut]
                results[name] = fut.result()
                progress[name] = "done"
                if len(results) < len(future_to_name):
                    update_debate_session(debate_id, {"finalization_progress": dict(progress)})

        verdict = results.get("verdict", "")
        timeline = results.get("timeline") if timeline_active else None
        resources = results.get("resources", [])

        complete_debate_session(
            debate_id,
            {
                "current_round_index": next_round_index,
                "transcript": _serialize_models(transcript),
                "metrics": _serialize_models(metrics),
                "debate_summary": debate_summary,
                "prev_beta": prev_beta,
                "verdict": verdict,
                "timeline": timeline.model_dump() if timeline else None,
                "resources": resources,
                "total_rounds": len(rounds),
                "interjections": list(interjections_history),
                "finalization_progress": dict(progress),
            },
        )
        _persist_to_agentcore_memory(debate_id, user_context, transcript, verdict)

        return CheckpointedDebateResponse(
            status="complete",
            debate_id=debate_id,
            transcript=transcript,
            verdict=verdict,
            timeline=timeline,
            metrics=metrics,
            completed_rounds=completed_rounds,
            total_rounds=len(rounds),
            resources=resources,
            next_round_number=None,
            finalization_progress=FinalizationProgress(**progress),
        )

    update_debate_session(
        debate_id,
        {
            "status": "paused",
            "current_round_index": next_round_index,
            "transcript": _serialize_models(transcript),
            "metrics": _serialize_models(metrics),
            "debate_summary": debate_summary,
            "prev_beta": prev_beta,
            "total_rounds": len(rounds),
            "interjections": list(interjections_history),
        },
    )

    return CheckpointedDebateResponse(
        status="paused",
        debate_id=debate_id,
        transcript=transcript,
        verdict="",
        timeline=None,
        metrics=metrics,
        completed_rounds=completed_rounds,
        total_rounds=len(rounds),
        resources=[],
        next_round_number=next_round_index + 1,
    )


def start_checkpointed_streaming(user_context: dict, user_id: str = "anonymous"):
    """Generator that streams the first round of a checkpointed debate via SSE events.

    Yields the same event types as continue_checkpointed_streaming():
      debate_start, round_start, token, agent_done, round_complete, session_update.

    After Round 1 completes, persists the session as paused and yields session_update.
    """
    debate_id = str(uuid.uuid4())
    category = detect_decision_category(
        user_context["path_a"],
        user_context["path_b"],
        constraints=user_context.get("constraints"),
        writing_samples=user_context.get("writing_samples"),
        template_id=user_context.get("template_id"),
    )
    rounds = get_rounds(category)
    tools = TOOL_MAP.get(category, [research_insight])
    alpha_persona, beta_persona = _assign_personas(user_context["path_a"], user_context["path_b"])

    enriched_context = {
        **user_context,
        "_category": category,
        "debate_id": debate_id,
        "user_id": user_id,
    }
    build_grounding_context(enriched_context, category)

    yield {
        "type": "debate_start",
        "debate_id": debate_id,
        "total_rounds": len(rounds),
    }

    result, debate_summary = yield from _stream_single_round(
        round_index=0,
        round_info=rounds[0],
        user_context=enriched_context,
        transcript=[],
        prev_beta=None,
        debate_summary="",
        interjection=None,
        tools=tools,
        alpha_persona=alpha_persona,
        beta_persona=beta_persona,
    )

    transcript = [result]
    metrics: list[RoundMetrics | None] = [result.metrics]
    prev_beta = result.beta if result.status == "completed" else None

    create_debate_session(
        debate_id=debate_id,
        user_id=user_id,
        user_input=enriched_context,
        session_data={
            "status": "paused",
            "current_round_index": 1,
            "transcript": _serialize_models(transcript),
            "metrics": _serialize_models(metrics),
            "debate_summary": debate_summary,
            "prev_beta": prev_beta,
            "category": category,
            "alpha_persona_label": alpha_persona["label"],
            "beta_persona_label": beta_persona["label"],
            "total_rounds": len(rounds),
        },
    )

    completed_rounds = len([r for r in transcript if r.status == "completed"])
    yield {
        "type": "session_update",
        "status": "paused",
        "debate_id": debate_id,
        "completed_rounds": completed_rounds,
        "total_rounds": len(rounds),
        "next_round_number": 2 if len(rounds) > 1 else None,
    }


def continue_checkpointed_streaming(debate_id: str, interjection: str | None = None):
    """Generator that streams one round of a checkpointed debate via SSE events.

    Yields the same event types as run_debate_token_streaming():
      round_start, token, agent_done, round_complete, session_update, complete.

    For non-final rounds: yields session_update after round_complete.
    For the final round: generates verdict/timeline/resources synchronously, then yields complete.
    """
    session = get_debate_session(debate_id)
    if not session:
        raise ValueError("Debate session not found.")

    if session.get("status") == "complete":
        raise ValueError("Debate session is already complete.")

    user_context = dict(session.get("input", {}) or {})
    category = session.get("category", "general")
    rounds = get_rounds(category)
    tools = TOOL_MAP.get(category, [research_insight])
    alpha_persona, beta_persona = _assign_personas(user_context["path_a"], user_context["path_b"])
    transcript = _deserialize_transcript(session.get("transcript", []))
    metrics = _deserialize_metrics(session.get("metrics", []))
    debate_summary = session.get("debate_summary", "")
    prev_beta = session.get("prev_beta")
    current_round_index = int(session.get("current_round_index", len(transcript)))

    interjections_history: list[str] = list(session.get("interjections", []) or [])
    user_context["_interjections"] = list(interjections_history)

    if interjection:
        debate_summary += f"\n[User interjects]: {interjection}\n"
        interjections_history.append(interjection)
        user_context["_interjections"] = list(interjections_history)

    if current_round_index >= len(rounds):
        raise ValueError("Debate session is already at the final round.")

    round_info = rounds[current_round_index]

    result, debate_summary = yield from _stream_single_round(
        round_index=current_round_index,
        round_info=round_info,
        user_context=user_context,
        transcript=transcript,
        prev_beta=prev_beta,
        debate_summary=debate_summary,
        interjection=interjection,
        tools=tools,
        alpha_persona=alpha_persona,
        beta_persona=beta_persona,
    )

    transcript.append(result)
    metrics.append(result.metrics)
    if result.status == "completed":
        prev_beta = result.beta

    next_round_index = current_round_index + 1
    completed_rounds = len([r for r in transcript if r.status == "completed"])

    if next_round_index >= len(rounds):
        update_debate_session(
            debate_id,
            {
                "status": "finalizing",
                "current_round_index": next_round_index,
                "transcript": _serialize_models(transcript),
                "metrics": _serialize_models(metrics),
                "debate_summary": debate_summary,
                "prev_beta": prev_beta,
                "verdict": "",
                "timeline": None,
                "resources": [],
                "total_rounds": len(rounds),
                "interjections": list(interjections_history),
            },
        )

        threading.Thread(
            target=_finalize_checkpointed_session_bundle,
            args=(
                debate_id,
                transcript,
                metrics,
                debate_summary,
                prev_beta,
                user_context,
                len(rounds),
                list(interjections_history),
            ),
            daemon=True,
        ).start()

        yield {
            "type": "session_update",
            "status": "finalizing",
            "debate_id": debate_id,
            "completed_rounds": completed_rounds,
            "total_rounds": len(rounds),
            "next_round_number": None,
            "verdict_ready": False,
        }
    else:
        update_debate_session(
            debate_id,
            {
                "status": "paused",
                "current_round_index": next_round_index,
                "transcript": _serialize_models(transcript),
                "metrics": _serialize_models(metrics),
                "debate_summary": debate_summary,
                "prev_beta": prev_beta,
                "total_rounds": len(rounds),
                "interjections": list(interjections_history),
            },
        )

        yield {
            "type": "session_update",
            "status": "paused",
            "debate_id": debate_id,
            "completed_rounds": completed_rounds,
            "total_rounds": len(rounds),
            "next_round_number": next_round_index + 1,
        }
