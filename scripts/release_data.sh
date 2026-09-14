#!/usr/bin/env bash
#
# Keep generated data in a GitHub Release instead of in git history.
#
# WHY
# ---
# Parquet is compressed binary, so git cannot delta it: every hourly run that
# changes one byte stores a whole new copy forever. This repo is currently
# ~121 MB of .git for 0.5 MB of actual code, and the data pipeline adds roughly
# a gigabyte a year. Release assets are not in git history -- uploading the same
# filename replaces the old one and the repo does not grow.
#
# It also stops every data update from triggering a Render redeploy. `main`
# goes back to changing only when code changes, which is what autoDeploy is
# supposed to mean.
#
# This is the same pattern nflverse uses, which is where get_nfl_pbp.py already
# pulls play-by-play from -- so the app has been consuming release assets for
# months. This just makes it publish them too.
#
# USAGE
#   scripts/release_data.sh pull data-mlb backend/data/mlb '*.parquet'
#   scripts/release_data.sh push data-mlb backend/data/mlb/starters.parquet ...
#
# The workflows invoke this as `bash scripts/release_data.sh ...` rather than
# executing it directly, on purpose: the repo is edited on Windows, where the
# Unix executable bit does not survive, so relying on file mode gives a
# "Permission denied" / exit 126 on the runner. Calling bash explicitly works
# whatever mode the file happens to be committed with.
#
# Requires `gh` (preinstalled on GitHub-hosted runners) and GH_TOKEN. The
# workflow's built-in secrets.GITHUB_TOKEN is enough -- it needs `contents:
# write`, which these workflows already declare. No PAT.

set -euo pipefail

mode="${1:?usage: release_data.sh <pull|push> <tag> ...}"
tag="${2:?missing release tag}"
shift 2

ensure_release() {
  if ! gh release view "$tag" >/dev/null 2>&1; then
    echo "creating release $tag"
    gh release create "$tag" \
      --title "Data: $tag" \
      --notes "Generated data files, replaced in place by scheduled workflows. Not a source release." \
      --latest=false
  fi
}

case "$mode" in
  pull)
    # Restores the previous run's output before the scripts run. This is not
    # optional: several of the builders are INCREMENTAL (bullpen_logs.parquet
    # appends to what is already there rather than refetching the season), and
    # once the files leave git the release is the only copy of that state.
    # Skipping this would silently turn an append into a bootstrap every run.
    dir="${1:?missing destination directory}"; shift
    mkdir -p "$dir"
    if ! gh release view "$tag" >/dev/null 2>&1; then
      echo "release $tag does not exist yet -- first run, nothing to restore"
      exit 0
    fi
    args=(download "$tag" --dir "$dir" --clobber)
    for pat in "$@"; do args+=(--pattern "$pat"); done
    # A release with no asset matching the pattern exits non-zero. On a first
    # run that is the expected state, not a failure.
    gh release "${args[@]}" || echo "no matching assets in $tag yet"
    ;;

  push)
    ensure_release
    existing=()
    for f in "$@"; do
      if [ -f "$f" ]; then
        existing+=("$f")
      else
        # Early in the day no lineup has posted, so the builder exits without
        # writing. Same tolerance the old commit step had.
        echo "missing (skipped): $f"
      fi
    done
    if [ ${#existing[@]} -eq 0 ]; then
      echo "nothing to upload"
      exit 0
    fi
    # --clobber replaces an asset of the same name. Two workflows writing
    # DIFFERENT assets under the same tag do not conflict, which is why this
    # needs none of the rebase-and-retry the git version did.
    gh release upload "$tag" "${existing[@]}" --clobber
    echo "uploaded ${#existing[@]} file(s) to $tag"
    ;;

  *)
    echo "unknown mode: $mode (expected pull or push)" >&2
    exit 2
    ;;
esac
