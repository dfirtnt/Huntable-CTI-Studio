#!/usr/bin/env bash

# Unlock the `main` branch so a release merge can land.
#
# `main` is held read-only between releases (see release_lock.sh). Run this
# script to temporarily remove branch protection, perform the release merge
# from `dev-io`, then run `release_lock.sh` to restore the lock.
#
# Requires: gh CLI authenticated with `repo` scope.

set -euo pipefail

REPO=${REPO:-dfirtnt/Huntable-CTI-Studio}
BRANCH=${BRANCH:-main}

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI not found. Install from https://cli.github.com/" >&2
  exit 1
fi

echo "Removing branch protection on ${REPO}:${BRANCH}..."
if gh api -X DELETE "repos/$REPO/branches/$BRANCH/protection" >/dev/null 2>&1; then
  echo "Branch $BRANCH is now UNLOCKED on $REPO."
  echo "Run scripts/release_lock.sh after the merge to restore protection."
else
  # 404 means no protection was set -- treat as success (idempotent).
  if gh api "repos/$REPO/branches/$BRANCH/protection" 2>&1 | grep -q "Branch not protected"; then
    echo "Branch $BRANCH already has no protection on $REPO (no-op)."
  else
    echo "Failed to remove protection. Check gh auth and repo permissions." >&2
    exit 1
  fi
fi
