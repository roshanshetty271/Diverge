"""Amazon Comprehend integration for sentiment analysis of debate rounds."""

import logging
from app.config import get_settings
from app.schemas import RoundSentiment, SentimentScores

logger = logging.getLogger("diverge.tools.comprehend")


def analyze_round_sentiment(alpha_text: str, beta_text: str) -> RoundSentiment | None:
    """Analyze sentiment of both agents' arguments using Amazon Comprehend.

    Returns None if Comprehend is not enabled or the call fails.
    Graceful degradation: sentiment is a nice-to-have, not critical.
    """
    settings = get_settings()
    if not settings.comprehend_enabled:
        return None

    try:
        import boto3
        client = boto3.client("comprehend", region_name=settings.aws_region)

        # Batch detect for efficiency (2 texts at once)
        response = client.batch_detect_sentiment(
            TextList=[alpha_text[:4500], beta_text[:4500]],
            LanguageCode="en",
        )

        results = response.get("ResultList", [])
        if len(results) < 2:
            return None

        def to_scores(r: dict) -> SentimentScores:
            scores = r.get("SentimentScore", {})
            return SentimentScores(
                positive=round(scores.get("Positive", 0), 3),
                negative=round(scores.get("Negative", 0), 3),
                neutral=round(scores.get("Neutral", 0), 3),
                mixed=round(scores.get("Mixed", 0), 3),
            )

        return RoundSentiment(
            path_a=to_scores(results[0]),
            path_b=to_scores(results[1]),
        )

    except Exception as e:
        logger.warning(f"Comprehend sentiment analysis failed: {type(e).__name__}: {e}")
        return None
