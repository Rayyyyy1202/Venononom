#!/usr/bin/env bash
# Local server for the GWM demo.
# Starts FastAPI (serves the scraped site at /, exposes /api/chat backed by OpenAI).
#
# Usage:  ./run.sh                  (EU site, port 8000)
#         ./run.sh 9000             (EU site, custom port)
#         GWM_SITE=th ./run.sh      (Thailand site)
#
# Requires:
#   pip install -r server/requirements.txt
#   cp .env.example .env  &&  edit OPENAI_API_KEY

set -e
PORT="${1:-8000}"
HERE="$(cd "$(dirname "$0")" && pwd)"
SITE="${GWM_SITE:-eu}"

if [ "$SITE" = "th" ]; then
  STATIC_DIR="public-th"
else
  STATIC_DIR="public"
fi

if [ ! -f "$HERE/$STATIC_DIR/index.html" ]; then
  echo "$STATIC_DIR/index.html not found. Run the scraper first:"
  echo "  pip install requests beautifulsoup4"
  echo "  python3 scripts/scrape.py $SITE"
  exit 1
fi

if [ ! -f "$HERE/.env" ]; then
  echo "warning: .env missing — /api/chat will return 500 until OPENAI_API_KEY is set."
  echo "  cp .env.example .env  &&  edit it"
fi

cd "$HERE"
echo "Serving GWM demo [$SITE] on http://localhost:$PORT  (Ctrl+C to stop)"
exec env GWM_SITE="$SITE" python3 -m uvicorn server.main:app --host 0.0.0.0 --port "$PORT"
