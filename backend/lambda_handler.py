"""AWS Lambda handler for Diverge API.

Uses Mangum to wrap FastAPI for Lambda.
Note: Mangum does NOT support SSE streaming (red flag fix: we use synchronous responses).
For the debate endpoint, use Lambda Function URL with longer timeout.
"""

from mangum import Mangum
from app.main import app

handler = Mangum(app, lifespan="off")
