"""Upload knowledge .md files to S3 for Bedrock Knowledge Base sourcing.

Usage:
    python -m scripts.upload_knowledge --bucket <bucket-name> [--prefix knowledge/]

Uploads all .md files from backend/data/knowledge/ to the specified S3 bucket.
These files are then ingested by Amazon Bedrock Knowledge Base.

Prerequisites:
    - AWS credentials configured
    - S3 bucket created
    - Bedrock Knowledge Base configured to use the S3 bucket as a data source
"""

import argparse
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "data" / "knowledge"


def upload_files(bucket: str, prefix: str = "knowledge/"):
    import boto3

    s3 = boto3.client("s3")
    md_files = sorted(KNOWLEDGE_DIR.glob("*.md"))

    if not md_files:
        logger.error(f"No .md files found in {KNOWLEDGE_DIR}")
        return

    for filepath in md_files:
        key = f"{prefix}{filepath.name}"
        logger.info(f"Uploading {filepath.name} -> s3://{bucket}/{key}")
        s3.upload_file(
            str(filepath),
            bucket,
            key,
            ExtraArgs={"ContentType": "text/markdown"},
        )

    logger.info(f"\nUploaded {len(md_files)} files to s3://{bucket}/{prefix}")
    logger.info("Next steps:")
    logger.info("  1. Go to Amazon Bedrock console -> Knowledge Bases")
    logger.info("  2. Create or update a Knowledge Base with this S3 data source")
    logger.info("  3. Sync the data source")
    logger.info("  4. Set DIVERGE_KB_ID=<your-kb-id> in your .env file")


def main():
    parser = argparse.ArgumentParser(description="Upload knowledge files to S3")
    parser.add_argument("--bucket", required=True, help="S3 bucket name")
    parser.add_argument("--prefix", default="knowledge/", help="S3 key prefix")
    args = parser.parse_args()

    upload_files(args.bucket, args.prefix)


if __name__ == "__main__":
    main()
