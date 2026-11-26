#!/usr/bin/env bash
# Deploys files from site/ to the S3 bucket and clears them from CloudFront.
#
# MODE (set by the workflow):
#   changed  - after a push to main: upload only the site/ files that changed
#   dry-run  - list every site/ file that a full deploy would upload; touches nothing in AWS
#   all      - upload every site/ file, then clear the whole CloudFront cache
#
# Files deleted from site/ are NOT deleted from S3. They are listed so you can remove them by hand.
set -euo pipefail

MODE="${MODE:-changed}"
SUMMARY="${GITHUB_STEP_SUMMARY:-/dev/stdout}"
upload=()
removed=()

if [[ "$MODE" == "changed" ]]; then
  BEFORE="${BEFORE_SHA:-}"
  if [[ -z "$BEFORE" || "$BEFORE" =~ ^0+$ ]] || ! git cat-file -e "$BEFORE^{commit}" 2>/dev/null; then
    echo "Can't find the previous commit; run the workflow by hand with 'all' instead."
    exit 1
  fi
  while IFS= read -r f; do [[ -n "$f" ]] && upload+=("$f"); done < <(git diff --no-renames --name-only --diff-filter=ACMT "$BEFORE" HEAD -- site/)
  while IFS= read -r f; do [[ -n "$f" ]] && removed+=("$f"); done < <(git diff --no-renames --name-only --diff-filter=D "$BEFORE" HEAD -- site/)
else
  while IFS= read -r f; do [[ -n "$f" ]] && upload+=("$f"); done < <(git ls-files site/)
fi

{
  echo "## Site deploy ($MODE)"
  echo
  if (( ${#upload[@]} )); then
    echo "**Files to upload (${#upload[@]}):**"
    for f in "${upload[@]}"; do echo "- \`${f#site/}\`"; done
  else
    echo "No site files changed."
  fi
  if (( ${#removed[@]} )); then
    echo
    echo "**Removed from site/ but still in S3 (delete by hand if intended):**"
    for f in "${removed[@]}"; do echo "- \`${f#site/}\`"; done
  fi
} >> "$SUMMARY"

if [[ "$MODE" == "dry-run" ]]; then
  echo "Dry run: nothing uploaded." >> "$SUMMARY"
  exit 0
fi
(( ${#upload[@]} )) || exit 0

: "${S3_BUCKET:?Set the S3_BUCKET repository variable}"
: "${CF_SITE_DIST:?Set the CF_SITE_DIST repository variable}"

for f in "${upload[@]}"; do
  echo "Uploading ${f#site/}"
  aws s3 cp "$f" "s3://$S3_BUCKET/${f#site/}" --only-show-errors
done

site_paths=()
photo_paths=()
if [[ "$MODE" == "all" ]]; then
  site_paths=("/*")
  photo_paths=("/parking-photos/*")
else
  for f in "${upload[@]}"; do
    p="/${f#site/}"
    p="${p// /%20}"                                             # CloudFront needs spaces written as %20
    site_paths+=("$p")
    [[ "$p" == "/index.html" ]] && site_paths+=("/")          # the home page is also cached as "/"
    [[ "$p" == /parking-photos/* ]] && photo_paths+=("$p")
  done
fi

aws cloudfront create-invalidation --distribution-id "$CF_SITE_DIST" --paths "${site_paths[@]}" \
  --query 'Invalidation.Id' --output text
echo "Cleared from the site's CloudFront: ${site_paths[*]}" >> "$SUMMARY"

if (( ${#photo_paths[@]} )) && [[ -n "${CF_PHOTO_DIST:-}" ]]; then
  aws cloudfront create-invalidation --distribution-id "$CF_PHOTO_DIST" --paths "${photo_paths[@]}" \
    --query 'Invalidation.Id' --output text
  echo "Cleared from the photo CloudFront: ${photo_paths[*]}" >> "$SUMMARY"
fi
echo "Done." >> "$SUMMARY"
