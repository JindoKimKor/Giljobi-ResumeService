#!/bin/bash
# =============================================================================
# run-local.sh — Build and run Resume Service locally (Docker)
# =============================================================================
# Mounts Claude CLI credentials from host.
# Reads Neon DB URLs from the local environment.
#
# Usage:
#   NEON_SD_DB_URL=... NEON_MT_DB_URL=... ./run-local.sh
#   NEON_SD_DB_URL=... NEON_MT_DB_URL=... ./run-local.sh --no-build
# =============================================================================

set -e

IMAGE_NAME="giljobi-resume-service"
CONTAINER_NAME="giljobi-resume"
PORT=8000

# Neon DB credentials must be supplied by the caller and must never be committed.
: "${NEON_SD_DB_URL:?Set NEON_SD_DB_URL in your local environment}"
: "${NEON_MT_DB_URL:?Set NEON_MT_DB_URL in your local environment}"

# Claude CLI credentials (host path)
CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"

# Stop existing
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

# Build (unless --no-build)
if [ "$1" != "--no-build" ]; then
    echo "Building $IMAGE_NAME..."
    docker build -t "$IMAGE_NAME" .
fi

# Run
echo "Starting $CONTAINER_NAME on port $PORT..."
MSYS_NO_PATHCONV=1 docker run -d --name "$CONTAINER_NAME" \
    -p "$PORT:$PORT" \
    -e NEON_SD_DB_URL="$NEON_SD_DB_URL" \
    -e NEON_MT_DB_URL="$NEON_MT_DB_URL" \
    -v "$CLAUDE_DIR:/root/.claude" \
    "$IMAGE_NAME"

echo ""
echo "=== Resume Service ==="
echo "Health:    http://localhost:$PORT/health"
echo "NOC list:  http://localhost:$PORT/noc-list"
echo "WebSocket: ws://localhost:$PORT/ws/analyze"
echo "Logs:      docker logs -f $CONTAINER_NAME"
echo "======================"
