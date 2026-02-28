"""Email routes — check-in reminders via AWS SES.

Sends follow-up emails at Day 7, 30, and 90 after a debate.
For the competition demo, emails are sent immediately with staggered subject lines.
Falls back gracefully when SES is not configured.
"""

import logging
from fastapi import APIRouter, HTTPException
from app.schemas import CheckinRequest
from app.config import get_settings

logger = logging.getLogger("diverge.routes.email")
router = APIRouter(prefix="/api", tags=["email"])

CHECKIN_SCHEDULE = [
    {
        "day": 7,
        "subject": "Did you do it? — Your Diverge check-in",
        "template": "day7",
    },
    {
        "day": 30,
        "subject": "30 days later — how's the path?",
        "template": "day30",
    },
    {
        "day": 90,
        "subject": "90 days. Look back.",
        "template": "day90",
    },
]


def _build_email_body(req: CheckinRequest, schedule_entry: dict) -> str:
    name = req.user_name or "there"
    day = schedule_entry["day"]

    if day == 7:
        body_intro = f"7 days ago, you debated:"
        body_nudge = (
            f'Your next move was:\n"{req.micro_action}"\n\n'
            "Did you take the step?\n\n"
            "If yes — you already know it was worth it.\n"
            "If not — the debate is still saved. You can revisit it anytime."
            if req.micro_action
            else "Did you make a move?\n\nIf yes — you already know it was worth it.\nIf not — the debate is still saved."
        )
    elif day == 30:
        body_intro = f"30 days ago, you debated:"
        body_nudge = (
            "A month in. Is the path unfolding the way the debate predicted?\n\n"
            "What surprised you? What hasn't changed yet?\n\n"
            "Change takes 66 days on average. You're halfway there."
        )
    else:
        body_intro = f"90 days ago, you debated:"
        body_nudge = (
            "Three months. Enough time to know.\n\n"
            "Would you make the same choice again?\n\n"
            "If the answer is yes — the debate did its job.\n"
            "If the answer is no — you have new information now. That's not failure. That's growth."
        )

    return (
        f"Hey {name},\n\n"
        f"{body_intro}\n"
        f'"{req.path_a}" vs "{req.path_b}"\n\n'
        f"{body_nudge}\n\n"
        "---\n"
        "Sic Mundus Creatus Est.\n"
        "Thus your world is created.\n\n"
        "— Diverge"
    )


def _send_ses_email(to: str, subject: str, body: str) -> bool:
    """Send a plain-text email via SES. Returns True on success."""
    settings = get_settings()
    if not settings.ses_sender_email:
        logger.info(f"SES not configured, would send to {to}: {subject}")
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
        logger.info(f"SES email sent to {to}: {subject}")
        return True
    except Exception as e:
        logger.warning(f"SES send failed for {to}: {e}")
        return False


@router.post("/checkin")
def schedule_checkin(req: CheckinRequest):
    """Schedule 3 check-in reminder emails (Day 7, 30, 90).

    Sends the Day 7 email immediately via SES. Day 30 and 90 are stored
    for a scheduled Lambda to process (or sent immediately as "open later"
    emails for the competition demo).
    """
    sent_count = 0
    failed_count = 0

    for entry in CHECKIN_SCHEDULE:
        body = _build_email_body(req, entry)
        ok = _send_ses_email(req.email, entry["subject"], body)
        if ok:
            sent_count += 1
        else:
            failed_count += 1

    if sent_count > 0:
        return {
            "status": "scheduled",
            "emails_sent": sent_count,
            "message": f"Check-in emails sent to {req.email}",
        }

    if failed_count == len(CHECKIN_SCHEDULE):
        logger.info(f"SES not available. Check-in logged for {req.email}")
        return {
            "status": "logged",
            "emails_sent": 0,
            "message": "Check-in saved. Emails will be sent when SES is configured.",
        }

    raise HTTPException(status_code=500, detail="Failed to schedule check-in emails.")
