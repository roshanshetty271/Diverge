"""Research insight tool — gives agents access to real-world statistics.

Two modes:
1. Bedrock Knowledge Base (when kb_id is configured): semantic search via bedrock-agent-runtime
2. Local fallback: keyword matching against pre-built chunks.json
"""

import json
import logging
from pathlib import Path
from strands import tool

logger = logging.getLogger("diverge.tools.knowledge")

CHUNKS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "knowledge" / "chunks.json"
_chunks_cache: list[dict] | None = None


def _load_chunks() -> list[dict]:
    global _chunks_cache
    if _chunks_cache is not None:
        return _chunks_cache
    try:
        _chunks_cache = json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning(f"chunks.json not found at {CHUNKS_PATH}. Run: python -m scripts.build_chunks")
        _chunks_cache = []
    return _chunks_cache


def _local_search(query: str, category: str, top_k: int = 3) -> list[dict]:
    """Simple keyword-overlap search against local chunks."""
    chunks = _load_chunks()
    query_words = set(query.lower().split())

    scored = []
    for chunk in chunks:
        cat_bonus = 5 if chunk.get("category") == category else 0
        keyword_overlap = len(query_words & set(chunk.get("keywords", [])))
        score = keyword_overlap + cat_bonus
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]


def _bedrock_search(query: str, kb_id: str, top_k: int = 3) -> list[dict]:
    """Search Bedrock Knowledge Base via retrieve API."""
    try:
        import boto3
        from app.config import get_settings
        settings = get_settings()
        region = settings.kb_region or settings.aws_region
        client = boto3.client("bedrock-agent-runtime", region_name=region)
        response = client.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": top_k}},
        )
        results = []
        for item in response.get("retrievalResults", []):
            content = item.get("content", {}).get("text", "")
            source = item.get("location", {}).get("s3Location", {}).get("uri", "unknown")
            results.append({"content": content, "source": source, "title": "Knowledge Base Result"})
        return results
    except Exception as e:
        logger.warning(f"Bedrock KB search failed, falling back to local: {e}")
        return []


def _fetch_chunks(query: str, category: str, top_k: int) -> list[dict]:
    """Shared fetch path: try Bedrock KB first, fall back to local chunks."""
    from app.config import get_settings
    settings = get_settings()

    results: list[dict] = []
    if settings.kb_id:
        results = _bedrock_search(query, settings.kb_id, top_k=top_k)

    if not results:
        results = _local_search(query, category, top_k=top_k)

    return results


def _retrieve_research_content(query: str, category: str, top_k: int = 1) -> str:
    """Return concatenated chunk content WITHOUT [Source: ...] prefixes.

    Used by the pre-retrieval grounding pipeline (backend/app/grounding.py) so
    the resulting blob can be injected directly into a system prompt without
    surfacing internal source paths to the model. Returns the sentinel string
    "No research data found for: <query>" when nothing matches, mirroring the
    behavior of the @tool wrapper below.
    """
    results = _fetch_chunks(query, category, top_k)
    if not results:
        return f"No research data found for: {query}"

    output_parts: list[str] = []
    for r in results:
        content = r.get("content", "")
        if len(content) > 800:
            content = content[:800] + "..."
        output_parts.append(content)

    return "\n\n---\n\n".join(output_parts)


@tool
def research_insight(query: str, category: str) -> str:
    """Look up real-world research and statistics relevant to a decision.

    Use this when you need specific data points to strengthen your argument:
    startup failure rates, career change statistics, relationship psychology,
    habit formation research, education ROI, or decision science findings.

    Args:
        query: What to look up (e.g. "startup failure rate", "habit formation time")
        category: Decision category (career, startup, relationship, health, education, general)
    """
    results = _fetch_chunks(query, category, top_k=3)
    if not results:
        return f"No research data found for: {query}"

    output_parts = []
    for r in results:
        content = r.get("content", "")
        if len(content) > 800:
            content = content[:800] + "..."
        source = r.get("source", "research database")
        output_parts.append(f"[Source: {source}]\n{content}")

    return "\n\n---\n\n".join(output_parts)
