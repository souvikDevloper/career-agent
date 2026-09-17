#!/usr/bin/env bash
# Builds Lambda artifacts without Docker: manylinux wheels for CPython 3.12 x86_64.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
rm -rf build && mkdir -p build/backend build/worker-browser

python3 -m pip install --quiet --upgrade pip
python3 -m pip install -r backend/requirements.txt -t build/backend \
  --platform manylinux2014_x86_64 --implementation cp --python-version 3.12 --only-binary=:all: --upgrade
cp -r backend/src/career_agent build/backend/
mkdir -p build/backend/career_agent/policies
cp policies/*.cedar build/backend/career_agent/policies/
find build/backend -name "__pycache__" -type d -prune -exec rm -rf {} +
find build/backend -name "*.dist-info" -type d -prune -exec sh -c 'rm -rf "$1"/RECORD' _ {} \;
echo "backend artifact: $(du -sh build/backend | cut -f1)"

cp worker-browser/package.json build/worker-browser/
cp -r worker-browser/src build/worker-browser/
( cd build/worker-browser && npm install --omit=dev --no-audit --no-fund --loglevel=error )
echo "browser artifact: $(du -sh build/worker-browser | cut -f1)"
