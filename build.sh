#!/usr/bin/env bash
# Render build step. Render's Python native-environment image doesn't
# guarantee Node.js is present, so this installs it via nvm before building
# the frontend -- backend/app/main.py serves whatever ends up in
# frontend/dist, so this replaces the old workflow of manually running
# `npm run build` locally and committing the dist folder.
set -euo pipefail

echo "--- installing backend dependencies ---"
# --no-cache-dir: pip's download cache is never reused between Render builds,
# it only makes the build bigger.
pip install --no-cache-dir -r requirements.txt

echo "--- installing node (via nvm) ---"
export NVM_DIR="$HOME/.nvm"
if [ ! -s "$NVM_DIR/nvm.sh" ]; then
  curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
fi
# shellcheck disable=SC1091
\. "$NVM_DIR/nvm.sh"
nvm install 20
nvm use 20

echo "--- building frontend ---"
cd frontend
npm ci --no-audit --no-fund
npm run build
cd ..

# ---------------------------------------------------------------------------
# Slim the build before Render uploads it.
#
# Render uploads this whole directory after the build finishes. It was ~380 MB,
# and "An internal error occurred when uploading the build" started showing up.
# None of the below is used by the running site -- the server only needs
# backend/ and the built frontend/dist -- so it's removed from the BUILD only.
# Nothing here touches the repo: every file is still in git, and still in your
# local checkout.
#   frontend/node_modules   ~250 MB, only needed to run the build above
#   predictions/            ~90 MB, the offline ML pipeline (its data + scripts)
#   train_table_*.parquet   ~22 MB, ML training tables at the repo root
#   pitcher-props/, docs/   a delivered patch folder and the GitHub Pages site
#   frontend/src, tests     source and tests, not needed once built
# ---------------------------------------------------------------------------
echo "--- trimming build output ---"
rm -rf frontend/node_modules frontend/src predictions pitcher-props docs backend/tests
rm -f train_table_*.parquet
find . -name "__pycache__" -type d -prune -exec rm -rf {} +
du -sh --exclude=.git . 2>/dev/null || true

echo "--- build.sh done ---"
