"""Text-to-speech route using Amazon Polly with Neural voices."""

import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.security.rate_limiter import check_rate_limit

logger = logging.getLogger("diverge.routes.tts")
router = APIRouter(prefix="/api", tags=["tts"])

VALID_VOICES = {
    "Matthew", "Stephen", "Joanna", "Ruth",
    "Gregory", "Danielle",
}


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    voice_id: str = Field("Matthew")
    use_ssml: bool = Field(False)


def _wrap_ssml(text: str) -> str:
    """Wrap plain text in SSML with natural-sounding prosody for debate delivery."""
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        '<speak>'
        '<prosody rate="95%" pitch="-2%">'
        f'{escaped}'
        '</prosody>'
        '</speak>'
    )


@router.post("/tts")
def synthesize_speech(req: TTSRequest, request: Request):
    """Synthesize speech from text using Amazon Polly Neural engine.

    Supports plain text and SSML for richer prosody control.
    Returns audio/mpeg stream. Frontend plays it directly via Audio element.
    """
    check_rate_limit(request, max_requests=10, window_seconds=300, endpoint="tts:burst")
    check_rate_limit(request, max_requests=40, window_seconds=3600, endpoint="tts")

    if req.voice_id not in VALID_VOICES:
        req.voice_id = "Matthew"

    try:
        import boto3
        from app.config import get_settings
        settings = get_settings()

        polly = boto3.client("polly", region_name=settings.aws_region)

        polly_params = {
            "OutputFormat": "mp3",
            "VoiceId": req.voice_id,
            "Engine": "neural",
        }

        if req.use_ssml:
            polly_params["Text"] = _wrap_ssml(req.text)
            polly_params["TextType"] = "ssml"
        else:
            polly_params["Text"] = req.text

        response = polly.synthesize_speech(**polly_params)

        audio_stream = response["AudioStream"].read()
        return Response(content=audio_stream, media_type="audio/mpeg")

    except Exception as e:
        logger.error(f"Polly TTS failed: {type(e).__name__}: {e}")
        raise HTTPException(status_code=502, detail="Speech synthesis unavailable.")
