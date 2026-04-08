"""Email routes and scheduled check-in processing via AWS SES."""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request

from app.config import get_settings
from app.db.dynamodb import create_checkin_records, get_due_checkins, update_checkin_record
from app.schemas import CheckinRequest, EmailResultsRequest
from app.security.rate_limiter import check_rate_limit

logger = logging.getLogger("diverge.routes.email")
router = APIRouter(prefix="/api", tags=["email"])

CHECKIN_SCHEDULE = [
    {
        "day": 7,
        "subject": "Did you do it? - Your Diverge check-in",
        "template": "day7",
    },
    {
        "day": 30,
        "subject": "30 days later - how's the path?",
        "template": "day30",
    },
    {
        "day": 90,
        "subject": "90 days. Look back.",
        "template": "day90",
    },
]


def _build_email_body(payload: dict, schedule_entry: dict) -> str:
    name = payload.get("user_name") or "there"
    day = schedule_entry["day"]
    micro_action = payload.get("micro_action") or ""
    path_a = payload.get("path_a") or "Option A"
    path_b = payload.get("path_b") or "Option B"

    if day == 7:
        body_intro = "7 days ago, you debated:"
        if micro_action:
            body_nudge = (
                f'Your next move was:\n"{micro_action}"\n\n'
                "Did you take the step?\n\n"
                "If yes - you already know it was worth it.\n"
                "If not - the debate is still saved. You can revisit it anytime."
            )
        else:
            body_nudge = (
                "Did you make a move?\n\n"
                "If yes - you already know it was worth it.\n"
                "If not - the debate is still saved."
            )
    elif day == 30:
        body_intro = "30 days ago, you debated:"
        body_nudge = (
            "A month in. Is the path unfolding the way the debate predicted?\n\n"
            "What surprised you? What hasn't changed yet?\n\n"
            "Change takes time. You are living the version of yourself you argued for."
        )
    else:
        body_intro = "90 days ago, you debated:"
        body_nudge = (
            "Three months. Enough time to know.\n\n"
            "Would you make the same choice again?\n\n"
            "If the answer is yes - the debate did its job.\n"
            "If the answer is no - you have new information now. That is not failure. That is growth."
        )

    return (
        f"Hey {name},\n\n"
        f"{body_intro}\n"
        f'"{path_a}" vs "{path_b}"\n\n'
        f"{body_nudge}\n\n"
        "---\n"
        "Sic Mundus Creatus Est.\n"
        "Thus your world is created.\n\n"
        "- Diverge"
    )


def _send_ses_email(to: str, subject: str, body: str) -> bool:
    """Send a plain-text email via SES. Returns True on success."""
    settings = get_settings()
    if not settings.ses_sender_email:
        logger.info("SES not configured, would send to %s: %s", to, subject)
        return False

    try:
        import boto3

        client = boto3.client("ses", region_name=settings.ses_region)
        client.send_email(
            Source=settings.ses_sender_email,
            Destination={"ToAddresses": [to]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
            },
        )
        logger.info("SES email sent to %s: %s", to, subject)
        return True
    except Exception as e:
        logger.warning("SES send failed for %s: %s", to, e)
        return False


def _build_checkin_record(req: CheckinRequest, schedule_entry: dict) -> dict:
    now = datetime.now(timezone.utc)
    send_at = now + timedelta(days=schedule_entry["day"])

    return {
        "checkin_id": uuid.uuid4().hex,
        "debate_id": req.debate_id or "",
        "email": req.email,
        "user_name": req.user_name,
        "path_a": req.path_a,
        "path_b": req.path_b,
        "micro_action": req.micro_action,
        "template": schedule_entry["template"],
        "subject": schedule_entry["subject"],
        "send_at": int(send_at.timestamp()),
        "status": "pending",
        "attempts": 0,
        "last_error": "",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "ttl": int((send_at + timedelta(days=180)).timestamp()),
    }


@router.post("/checkin")
def schedule_checkin(req: CheckinRequest, request: Request):
    """Schedule 3 delayed check-in reminder emails (Day 7, 30, 90)."""
    check_rate_limit(request, max_requests=2, window_seconds=900, endpoint="checkin:burst")
    check_rate_limit(request, max_requests=6, window_seconds=3600, endpoint="checkin")
    settings = get_settings()
    if not (
        settings.ses_sender_email
        and settings.checkins_table
        and settings.checkins_scheduler_enabled
    ):
        logger.info("Check-in scheduling unavailable for %s", req.email)
        return {
            "status": "logged",
            "emails_sent": 0,
            "message": "Email scheduling is not active right now.",
        }

    try:
        records = [_build_checkin_record(req, entry) for entry in CHECKIN_SCHEDULE]
        scheduled_count = create_checkin_records(records)
        return {
            "status": "scheduled",
            "emails_sent": 0,
            "scheduled_count": scheduled_count,
            "message": f"Check-in emails scheduled for {req.email}",
        }
    except Exception as e:
        logger.error("Failed to schedule check-ins for %s: %s", req.email, e)
        raise HTTPException(status_code=500, detail="Failed to schedule check-in emails.") from e


def process_due_checkins(limit: int = 25) -> dict:
    """Process scheduled check-ins whose send time has arrived."""
    now = datetime.now(timezone.utc)
    due_items = get_due_checkins(limit=limit)
    sent = 0
    retried = 0
    failed = 0

    for item in due_items:
        schedule_entry = next(
            (entry for entry in CHECKIN_SCHEDULE if entry["template"] == item.get("template")),
            None,
        )
        if not schedule_entry:
            update_checkin_record(
                item["checkin_id"],
                {"status": "failed", "last_error": "Unknown template"},
            )
            failed += 1
            continue

        body = _build_email_body(item, schedule_entry)
        ok = _send_ses_email(item["email"], item["subject"], body)

        if ok:
            update_checkin_record(
                item["checkin_id"],
                {
                    "status": "sent",
                    "sent_at": now.isoformat(),
                    "last_error": "",
                },
            )
            sent += 1
            continue

        attempts = int(item.get("attempts", 0)) + 1
        if attempts >= 3:
            update_checkin_record(
                item["checkin_id"],
                {
                    "status": "failed",
                    "attempts": attempts,
                    "last_error": "SES send failed",
                },
            )
            failed += 1
        else:
            retry_at = now + timedelta(hours=6)
            update_checkin_record(
                item["checkin_id"],
                {
                    "status": "pending",
                    "attempts": attempts,
                    "send_at": int(retry_at.timestamp()),
                    "last_error": "SES send failed",
                },
            )
            retried += 1

    return {
        "checked": len(due_items),
        "sent": sent,
        "retried": retried,
        "failed": failed,
    }


def _build_results_email(req: EmailResultsRequest) -> str:
    """Build a plain-text results email with verdict and resources."""
    lines = [
        f'Your Diverge Decision: "{req.path_a}" vs "{req.path_b}"',
        "=" * 50,
        "",
    ]

    if req.verdict_summary:
        lines.append("THE VERDICT")
        lines.append("-" * 30)
        lines.append(req.verdict_summary)
        lines.append("")

    if req.resources:
        lines.append("WHAT TO EXPLORE NEXT")
        lines.append("-" * 30)
        for r in req.resources:
            r_type = r.get("type", "").upper()
            title = r.get("title", "")
            author = r.get("author", "")
            why = r.get("why", "")
            url = r.get("url", "")
            lines.append(f"[{r_type}] {title} - {author}")
            if why:
                lines.append(f"  {why}")
            if url:
                lines.append(f"  {url}")
            lines.append("")

    lines.extend(
        [
            "---",
            "Sic Mundus Creatus Est.",
            "Thus your world is created.",
            "",
            "- Diverge",
        ]
    )

    return "\n".join(lines)


@router.post("/email-results")
def send_results_email(req: EmailResultsRequest, request: Request):
    """Email debate results and resource recommendations to the user."""
    check_rate_limit(request, max_requests=3, window_seconds=900, endpoint="email-results:burst")
    check_rate_limit(request, max_requests=10, window_seconds=3600, endpoint="email-results")
    body = _build_results_email(req)
    subject = f"Your Diverge Decision: {req.path_a} vs {req.path_b}"

    ok = _send_ses_email(req.email, subject, body)
    if ok:
        return {"status": "sent", "message": f"Results sent to {req.email}"}

    return {
        "status": "fallback",
        "message": "Email service not available. Copy your results below.",
        "body": body,
    }
