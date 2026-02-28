#!/usr/bin/env bash
set -euo pipefail

# ─── Diverge Deploy Script ──────────────────────────────────────
# Builds and deploys the full stack to AWS.
# Run: ./deploy.sh [dev|prod]

STAGE="${1:-prod}"
STACK_NAME="diverge-${STAGE}"
REGION="${AWS_REGION:-us-east-1}"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  DIVERGE — Deploying to ${STAGE}         ║"
echo "║  Sic Mundus Creatus Est                  ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── Step 1: SAM Build ───────────────────────────────────────────
echo "→ Building SAM application..."
sam build --template-file template.yaml --use-container 2>/dev/null || sam build --template-file template.yaml

# ── Step 2: SAM Deploy ──────────────────────────────────────────
echo "→ Deploying SAM stack: ${STACK_NAME}..."
sam deploy \
  --stack-name "${STACK_NAME}" \
  --region "${REGION}" \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --parameter-overrides "Stage=${STAGE}" \
  --resolve-s3 \
  --no-confirm-changeset \
  --no-fail-on-empty-changeset

# ── Step 3: Get Outputs ─────────────────────────────────────────
echo "→ Fetching stack outputs..."
OUTPUTS=$(aws cloudformation describe-stacks \
  --stack-name "${STACK_NAME}" \
  --region "${REGION}" \
  --query "Stacks[0].Outputs" \
  --output json)

_get_output() {
  echo "$OUTPUTS" | python3 -c "import sys,json; [print(o['OutputValue']) for o in json.load(sys.stdin) if o['OutputKey']=='$1']"
}

CF_URL=$(_get_output CloudFrontUrl)
BUCKET=$(_get_output FrontendBucket)
POOL_ID=$(_get_output UserPoolId)
CLIENT_ID=$(_get_output UserPoolClientId)
COGNITO_DOMAIN=$(_get_output CognitoDomain)
DIST_ID=$(_get_output CloudFrontDistributionId)

# Validate critical outputs
for var_name in CF_URL BUCKET POOL_ID CLIENT_ID; do
  eval "val=\$$var_name"
  if [ -z "$val" ]; then
    echo "ERROR: Failed to get $var_name from stack outputs"
    exit 1
  fi
done

# ── Step 4: Build Frontend ──────────────────────────────────────
echo "→ Building frontend with production config..."
cd frontend

# Write production .env
cat > .env.production << EOF
VITE_API_URL=${CF_URL}
VITE_COGNITO_REGION=${REGION}
VITE_COGNITO_USER_POOL_ID=${POOL_ID}
VITE_COGNITO_CLIENT_ID=${CLIENT_ID}
VITE_COGNITO_DOMAIN=${COGNITO_DOMAIN}
VITE_REDIRECT_URI=${CF_URL}
EOF

npm install --silent
npm run build

# ── Step 5: Upload to S3 ────────────────────────────────────────
echo "→ Uploading frontend to S3..."
aws s3 sync dist/ "s3://${BUCKET}/" \
  --region "${REGION}" \
  --delete \
  --cache-control "public, max-age=31536000, immutable" \
  --exclude "index.html" \
  --exclude "*.json"

# index.html should not be cached (SPA entry point)
aws s3 cp dist/index.html "s3://${BUCKET}/index.html" \
  --region "${REGION}" \
  --cache-control "no-cache, no-store, must-revalidate"

cd ..

# ── Step 6: Invalidate CloudFront ────────────────────────────────
echo "→ Invalidating CloudFront cache..."
if [ -n "$DIST_ID" ]; then
  aws cloudfront create-invalidation \
    --distribution-id "$DIST_ID" \
    --paths "/*" > /dev/null
  echo "  CloudFront invalidation started for ${DIST_ID}"
else
  echo "  WARNING: No CloudFront distribution ID found — skipping invalidation"
fi

# ── Done ─────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  DEPLOYED SUCCESSFULLY                   ║"
echo "╠══════════════════════════════════════════╣"
echo "║  App:     ${CF_URL}"
echo "║  Cognito: ${COGNITO_DOMAIN}"
echo "║  Pool ID: ${POOL_ID}"
echo "╚══════════════════════════════════════════╝"
echo ""
