#!/usr/bin/env bash
# Use the hooks tracked in this repo. Git doesn't keep this setting in a clone, so run it once per clone.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
chmod +x tools/git-hooks/*
git config core.hooksPath tools/git-hooks
echo "Hooks installed from tools/git-hooks."
