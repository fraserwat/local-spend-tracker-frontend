#!/usr/bin/env bash
# git pre-push hook: refuse any push whose remote ref is main.
set -euo pipefail

while read -r local_ref local_sha remote_ref remote_sha; do
  if [[ "$remote_ref" == "refs/heads/main" ]]; then
    echo "Blocked: push targets main. Push a feature branch and open a PR instead." >&2
    exit 1
  fi
done

exit 0
