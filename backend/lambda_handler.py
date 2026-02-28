"""AWS Lambda handler for Diverge API.

Supports two invocation paths:
  1. API Gateway / Function URL → Mangum wraps FastAPI (default)
  2. Bedrock Agent Action Group → routes to dedicated handler

X-Ray tracing patches boto3 for automatic subsegment creation.
"""

import os

if os.environ.get("AWS_XRAY_DAEMON_ADDRESS") or os.environ.get("_X_AMZN_TRACE_ID"):
    from aws_xray_sdk.core import xray_recorder, patch_all
    xray_recorder.configure(service="diverge-api")
    patch_all()

from mangum import Mangum
from app.main import app

_mangum_handler = Mangum(app, lifespan="off")


def handler(event, context):
    from app.bedrock_agent_handler import is_bedrock_agent_event, handle_bedrock_agent_event
    if is_bedrock_agent_event(event):
        return handle_bedrock_agent_event(event)
    return _mangum_handler(event, context)
