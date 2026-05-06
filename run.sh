#!/usr/bin/env bash
# Local server for the GWM demo.
# Starts FastAPI (serves the scraped site at /, exposes /api/chat backed by OpenAI).
#
# Usage:  ./run.sh           (defaults to port 8000)
#         ./run.sh 9000      (custom port)
#
# Requires:
#   pip install -r server/requirements.txt
#   cp .env.example .env  &&  edit OPENAI_API_KEY

set -e
PORT="${1:-8000}"
HERE="$(cd "$(dirname "$0")" && pwd)"

if [ ! -f "$HERE/public/index.html" ]; then
  echo "public/index.html not found. Run the scraper first:"
  echo "  pip install requests beautifulsoup4"
  echo "  python3 scripts/scrape.py"
  exit 1
fi

if [ ! -f "$HERE/.env" ]; then
  echo "warning: .env missing — /api/chat will return 500 until OPENAI_API_KEY is set."
  echo "  cp .env.example .env  &&  edit it"
fi

cd "$HERE"
echo "Serving GWM demo on http://localhost:$PORT  (Ctrl+C to stop)"
exec python3 -m uvicorn server.main:app --host 0.0.0.0 --port "$PORT"
