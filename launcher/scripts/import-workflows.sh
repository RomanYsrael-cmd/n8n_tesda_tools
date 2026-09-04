#!/usr/bin/env sh
set -eu
existing="$(n8n list:workflow 2>/dev/null || true)"
missing=0
for workflow_id in tesda-normalize-v1 tesda-generate-v1 tesda-build-import-v1 tesda-error-v1; do
  echo "$existing" | grep -q "$workflow_id" || missing=1
done
if [ "$missing" -eq 1 ]; then
  n8n import:workflow --separate --input=/workflows
  for workflow_id in tesda-normalize-v1 tesda-generate-v1 tesda-build-import-v1 tesda-error-v1; do
    n8n publish:workflow --id="$workflow_id"
  done
  echo "Module Builder workflows imported and published from version-controlled JSON."
else
  echo "Module Builder workflows are already installed; no duplicate import was needed."
fi
