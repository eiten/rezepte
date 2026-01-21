#!/usr/bin/env bash

# -----------------------------------------------------------------------------
# Tailwind CSS Watcher Script
# -----------------------------------------------------------------------------

# Resolve the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Navigate to the project root (assuming tools/ is one level deep)
# This ensures the relative paths for css files work regardless of where you call the script from
PROJECT_ROOT="$SCRIPT_DIR/.."

if ! cd "$PROJECT_ROOT"; then
    echo "Error: Could not change directory to project root."
    exit 1
fi

# Check if npx is installed/available in the current environment
if ! command -v npx &> /dev/null; then
    echo "Error: 'npx' is not found. Please ensure Node.js is installed and in your PATH."
    exit 1
fi

echo "Starting Tailwind CSS watcher from: $(pwd)"
echo "---------------------------------------------"

# Run the watcher
npx @tailwindcss/cli -i ./static/css/src.css -o ./static/css/main.css --watch