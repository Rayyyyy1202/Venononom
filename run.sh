#!/usr/bin/env bash
# Local preview server for the scraped GWM EU homepage demo.
# Usage:  ./run.sh           (defaults to port 8000)
#         ./run.sh 9000      (custom port)

set -e
PORT="${1:-8000}"
HERE="$(cd "$(dirname "$0")" && pwd)"

if [ ! -f "$HERE/site/index.html" ]; then
  echo "site/index.html not found. Run the scraper first:"
  echo "  pip install requests beautifulsoup4"
  echo "  python3 scripts/scrape.py"
  exit 1
fi

cd "$HERE/site"
echo "Serving $HERE/site on http://localhost:$PORT  (Ctrl+C to stop)"
exec python3 -m http.server "$PORT"
