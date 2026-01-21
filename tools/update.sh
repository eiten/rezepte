#!/usr/bin/env bash
set -euo pipefail

SERVICE=${SERVICE:-rezepte}
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"/..

TAG="${1:-}"

echo "Stopping service: $SERVICE"
sudo systemctl stop "$SERVICE"

echo "Fetching tags and main"
git fetch --tags origin
git fetch origin main

if [[ -n "$TAG" ]]; then
  echo "Checking out tag: $TAG"
  git checkout -f "tags/$TAG"
else
  echo "No tag specified; checking out latest tag"
  LATEST_TAG="$(git tag --list 'v*' --sort=-version:refname | head -n1)"
  git checkout -f "tags/$LATEST_TAG"
fi

echo "Clearing cache"
rm -rf cache

echo "Starting service: $SERVICE"
sudo systemctl start "$SERVICE"
