"""Scheduled Lambda entrypoint for processing due Diverge check-ins."""

from app.routes.email import process_due_checkins


def handler(event, context):
    return process_due_checkins()
