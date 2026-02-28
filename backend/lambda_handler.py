"""AWS Lambda handler for Diverge API.

Uses Mangum to wrap FastAPI for Lambda.
X-Ray tracing patches boto3 for automatic subsegment creation.
"""

import os

if os.environ.get("AWS_XRAY_DAEMON_ADDRESS") or os.environ.get("_X_AMZN_TRACE_ID"):
    from aws_xray_sdk.core import xray_recorder, patch_all
    xray_recorder.configure(service="diverge-api")
    patch_all()

from mangum import Mangum
from app.main import app

handler = Mangum(app, lifespan="off")
