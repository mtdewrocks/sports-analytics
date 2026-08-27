#!/usr/bin/env bash
# Render build step. Render's Python native-environment image doesn't
# guarantee Node.js is present, so this installs it via nvm before building
# the frontend -- backend/app/main.py serves whatever ends up in
# frontend/dist, so this replaces the old workflow of manually running
# `npm run build` locally and committing the dist folder.
set -euo pipefail

echo "--- installing backend dependencies ---"
pip install -r requirements.txt

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
npm ci
npm run build
cd ..

echo "--- build.sh done ---"
