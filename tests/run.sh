#!/usr/bin/env bash
# Everything CI used to do, run locally. No network, no API key, no cost.
#   tests/run.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "── engine imports"
python3 -c "import engine.room, engine.project, engine.drawings, engine.prompts, engine.render, engine.cli, engine.workspace, engine.catalog, engine.server, engine.mcp, engine.imagesafe, engine.consult, engine.chrome" \
  && echo "   ok"

echo "── unit tests (fallback YAML parser, room geometry, example project)"
python3 tests/test_config.py | sed 's/^/   /'

echo "── workspace, catalog, image safety, server, MCP (isolated data home)"
python3 tests/test_services.py 2>/dev/null | sed 's/^/   /'

echo "── catalog entries validate"
for f in catalog/*.yml; do ./bin/design catalog check "$(basename "$f" .yml)" | tail -1 | sed 's/^/   /'; done

echo "── example project validates"
./bin/design check --project study-terrace | sed 's/^/   /'

echo "── templates scaffold and validate"
for t in room kitchen; do
  rm -rf "projects/_t-$t"
  ./bin/design init "_t-$t" --from "$t" >/dev/null
  ./bin/design check --project "_t-$t" | tail -1 | sed "s/^/   $t: /"
  rm -rf "projects/_t-$t"
done

echo "── drawings rasterise"
./bin/design approve room-model --project study-terrace --note "local test" >/dev/null
./bin/design drawings --shell --project study-terrace >/dev/null
if python3 -c "import sys; from engine import chrome; sys.exit(0 if chrome.find() else 1)"; then
  test -s projects/study-terrace/drawings/_shell-plan.png || { echo "   FAIL: no PNG written"; exit 1; }
  echo "   ok"
else
  echo "   skipped: no Chrome/Chromium (nix develop provides one)"
fi

echo
echo "all checks passed"
