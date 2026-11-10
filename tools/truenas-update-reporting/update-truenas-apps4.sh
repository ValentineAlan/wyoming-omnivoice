#!/bin/bash

set -u

HELPER_DIR="/mnt/Decathlon/appdata/truenas-update-reporting"
HELPER="$HELPER_DIR/custom_app_changelog.py"
RUN_METADATA="$(mktemp -d)"
SUCCESS_APPS="$(mktemp)"
LAST_REPORT="$HELPER_DIR/last-report.md"

is_custom_app() {
  jq -e '.custom_app == true or .metadata.name == "ix-app"' >/dev/null <<<"$1"
}

capture_custom() {
  python3 "$HELPER" capture "$1" "$2" || printf '{}\n' >"$2"
}

REPORT_FILE="$(mktemp)"
ERROR_FILE="$(mktemp)"
MATCHED_RELEASES_FILE="$(mktemp)"

# Prevent overlapping cron/manual runs from changing the same app's state.
exec 9>/var/run/update-truenas-apps.lock
flock -n 9 || { echo "Another app-update run is active." >&2; exit 1; }

RESTORE_APP=""
cleanup() {
  local rc=$?
  trap - EXIT
  if [ -n "$RESTORE_APP" ]; then
    echo "Restoring stopped state for $RESTORE_APP during cleanup." >&2
    midclt call --job app.stop "$RESTORE_APP" >&2 || rc=1
  fi
  rm -f "$REPORT_FILE" "$ERROR_FILE" "$MATCHED_RELEASES_FILE"
  rm -f "$SUCCESS_APPS"
  rm -rf -- "$RUN_METADATA"
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

normalise_version() {
  printf '%s' "$1" |
    sed -E '
      s#^refs/tags/##
      s/^[vV]//
      s/^(release|version)[-_.]?[vV]?//
    '
}

version_gt() {
  local left="$1"
  local right="$2"
  local highest

  [ "$left" != "$right" ] || return 1

  highest="$(
    printf '%s\n%s\n' "$left" "$right" |
      sort -V |
      tail -n1
  )"

  [ "$highest" = "$left" ]
}

version_le() {
  local left="$1"
  local right="$2"
  local highest

  highest="$(
    printf '%s\n%s\n' "$left" "$right" |
      sort -V |
      tail -n1
  )"

  [ "$highest" = "$right" ]
}

full_changelog_link() {
  local changelog_url="$1"

  if [ -n "$changelog_url" ]; then
    printf '[View full upstream release history](%s)\n' "$changelog_url"
  else
    printf '%s\n' "No upstream release-history URL was supplied."
  fi
}

extract_markdown_version_range() {
  local markdown="$1"
  local from_version="$2"
  local target_version="$3"
  local line
  local heading_version
  local include_section=false

  while IFS= read -r line; do
    # Identify Markdown version headings such as:
    #
    # ## v2.18.0
    # ## 2.18.0
    # ## [2.18.0] - 2026-08-25
    heading_version="$(
      sed -nE '
        s/^#{1,6}[[:space:]]+[^0-9]*[vV]?([0-9]+([.][0-9A-Za-z_-]+)+).*/\1/p
      ' <<<"$line"
    )"

    if [ -n "$heading_version" ]; then
      heading_version="$(normalise_version "$heading_version")"

      if version_gt "$heading_version" "$from_version" &&
         version_le "$heading_version" "$target_version"; then
        include_section=true
      else
        include_section=false
      fi
    fi

    if [ "$include_section" = true ]; then
      printf '%s\n' "$line"
    fi
  done <<<"$markdown"
}

get_relevant_changelog() {
  local app_json="$1"
  local summary="$2"

  local from_upstream
  local target_human
  local target_upstream
  local from_normalised
  local target_normalised
  local changelog_url
  local embedded_changelog

  local github_owner
  local github_repo
  local github_branch
  local github_path
  local raw_changelog_url
  local markdown_changelog
  local relevant_markdown

  local releases
  local release_json
  local release_tag
  local release_version
  local match_count

  changelog_url="$(
    jq -r '.metadata.changelog_url // empty' <<<"$app_json"
  )"

  from_upstream="$(
    jq -r '
      .metadata.app_version //
      (.human_version // "" | split("_")[0]) //
      empty
    ' <<<"$app_json"
  )"

  target_human="$(
    jq -r '
      .upgrade_human_version //
      .latest_human_version //
      empty
    ' <<<"$summary"
  )"

  target_upstream="${target_human%%_*}"

  # Prefer changelog text embedded directly in the TrueNAS upgrade summary.
  embedded_changelog="$(
    jq -r '
      [
        .available_versions_for_upgrade[]?
        | select(
            .changelog != null and
            (.changelog | type) == "string" and
            (.changelog | length) > 0
          )
        | "#### \(.human_version // .version)\n\n\(.changelog)"
      ]
      | join("\n\n")
    ' <<<"$summary"
  )"

  if [ -n "$embedded_changelog" ]; then
    printf '%s\n' "$embedded_changelog"
    return
  fi

  if [ -z "$from_upstream" ] ||
     [ -z "$target_upstream" ] ||
     [ "$target_upstream" = "Unknown" ]; then
    echo "The installed or target upstream version could not be identified."
    echo
    full_changelog_link "$changelog_url"
    return
  fi

  from_normalised="$(normalise_version "$from_upstream")"
  target_normalised="$(normalise_version "$target_upstream")"

  # An unchanged upstream version means that the TrueNAS catalogue package
  # changed but the underlying application did not.
  if [ "$from_normalised" = "$target_normalised" ]; then
    echo "**TrueNAS packaging-only update**"
    echo
    echo "The upstream application remains at version $target_upstream."
    echo
    echo "This update changes the TrueNAS catalogue package rather than the upstream application."
    echo
    full_changelog_link "$changelog_url"
    return
  fi

  if [ -z "$changelog_url" ]; then
    echo "No embedded changelog or upstream release-history URL was supplied."
    return
  fi

  # Refuse comparisons where the extracted versions do not start numerically.
  if [[ ! "$from_normalised" =~ ^[0-9] ]] ||
     [[ ! "$target_normalised" =~ ^[0-9] ]]; then
    echo "The installed and target versions use a format that could not be compared reliably."
    echo
    echo "- Installed upstream version: $from_upstream"
    echo "- Target upstream version: $target_upstream"
    echo
    full_changelog_link "$changelog_url"
    return
  fi

  #
  # GitHub Markdown changelog
  #
  # Example:
  # https://github.com/Tautulli/Tautulli/blob/master/CHANGELOG.md
  #
  if [[ "$changelog_url" =~ ^https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.*)$ ]]; then
    github_owner="${BASH_REMATCH[1]}"
    github_repo="${BASH_REMATCH[2]}"
    github_branch="${BASH_REMATCH[3]}"
    github_path="${BASH_REMATCH[4]}"

    raw_changelog_url="https://raw.githubusercontent.com/$github_owner/$github_repo/$github_branch/$github_path"

    markdown_changelog="$(
      curl \
        --silent \
        --show-error \
        --fail \
        --connect-timeout 15 \
        --max-time 45 \
        "$raw_changelog_url" 2>/dev/null
    )" || markdown_changelog=""

    if [ -z "$markdown_changelog" ]; then
      echo "The upstream Markdown changelog could not be downloaded."
      echo
      full_changelog_link "$changelog_url"
      return
    fi

    relevant_markdown="$(
      extract_markdown_version_range \
        "$markdown_changelog" \
        "$from_normalised" \
        "$target_normalised"
    )"

    if [ -n "$relevant_markdown" ]; then
      echo "Changes from upstream version **$from_upstream** to **$target_upstream**:"
      echo
      printf '%s\n' "$relevant_markdown"
      echo
      full_changelog_link "$changelog_url"
      return
    fi

    echo "The upstream changelog was retrieved, but its version sections could not be matched reliably."
    echo
    echo "- Installed upstream version: $from_upstream"
    echo "- Target upstream version: $target_upstream"
    echo
    full_changelog_link "$changelog_url"
    return
  fi

  #
  # GitHub Releases
  #
  # Example:
  # https://github.com/sabnzbd/sabnzbd/releases
  #
  if [[ ! "$changelog_url" =~ ^https://github\.com/([^/]+)/([^/]+) ]]; then
    echo "The upstream changelog is not hosted on a supported GitHub source."
    echo
    full_changelog_link "$changelog_url"
    return
  fi

  github_owner="${BASH_REMATCH[1]}"
  github_repo="${BASH_REMATCH[2]}"

  github_repo="${github_repo%.git}"
  github_repo="${github_repo%%/*}"

  releases="$(
    curl \
      --silent \
      --show-error \
      --fail \
      --connect-timeout 15 \
      --max-time 45 \
      --header "Accept: application/vnd.github+json" \
      --header "X-GitHub-Api-Version: 2022-11-28" \
      "https://api.github.com/repos/$github_owner/$github_repo/releases?per_page=100" \
      2>/dev/null
  )" || releases=""

  if [ -z "$releases" ] ||
     ! jq -e 'type == "array"' >/dev/null 2>&1 <<<"$releases"; then
    echo "The GitHub release lookup failed or returned an invalid response."
    echo
    full_changelog_link "$changelog_url"
    return
  fi

  : >"$MATCHED_RELEASES_FILE"

  # Select every release in this interval:
  #
  # installed upstream version < release version <= target upstream version
  while IFS= read -r release_json; do
    release_tag="$(
      jq -r '.tag_name // empty' <<<"$release_json"
    )"

    if [ -z "$release_tag" ]; then
      continue
    fi

    release_version="$(normalise_version "$release_tag")"

    if [ -z "$release_version" ] ||
       [[ ! "$release_version" =~ ^[0-9] ]]; then
      continue
    fi

    if version_gt "$release_version" "$from_normalised" &&
       version_le "$release_version" "$target_normalised"; then
      printf '%s\n' "$release_json" >>"$MATCHED_RELEASES_FILE"
    fi
  done < <(
    jq -c '
      .[]
      | select((.draft // false) == false)
    ' <<<"$releases"
  )

  if [ -s "$MATCHED_RELEASES_FILE" ]; then
    match_count="$(wc -l <"$MATCHED_RELEASES_FILE")"
  else
    match_count=0
  fi

  if [ "$match_count" -eq 0 ]; then
    echo "No upstream releases could be matched reliably for this version range."
    echo
    echo "- Installed upstream version: $from_upstream"
    echo "- Target upstream version: $target_upstream"
    echo
    full_changelog_link "$changelog_url"
    return
  fi

  echo "Changes from upstream version **$from_upstream** to **$target_upstream**:"
  echo

  # GitHub returns releases newest-first. Sort the selected releases
  # chronologically before including them in the report.
  jq -rs '
    sort_by(
      .published_at //
      .created_at //
      ""
    )
    | .[]
    | "#### \(
        if (.name // "") != "" then
          .name
        else
          .tag_name
        end
      )

- **Release tag:** \(.tag_name)
- **Published:** \(
    .published_at //
    .created_at //
    "Unknown"
  )

\(
  if (.body // "") != "" then
    .body
  else
    "No release-note text was supplied for this release."
  end
)

[View this release on GitHub](\(.html_url))
"
  ' "$MATCHED_RELEASES_FILE"

  echo
  full_changelog_link "$changelog_url"
}

clean_job_error() {
  local error_file="$1"

  tr '\r' '\n' <"$error_file" |
    sed -E '
      s/\x1B\[[0-9;?]*[ -/]*[@-~]//g
      /Status: \(none\)/d
      /Total Progress:/d
      /^[[:space:]]*$/d
    '
}

# TrueNAS Docker Apps API (25.10 / 26 beta / 27):
# midclt call --job app.start APP_NAME
# midclt call --job app.stop APP_NAME
# RUNNING is the API state corresponding to a started app.
app_state() {
  local instance
  instance="$(midclt call app.get_instance "$1")" || return 1
  jq -er '.state | select(type == "string" and length > 0)' <<<"$instance"
}

wait_app_state() {
  local app="$1" target="$2" state
  local deadline=$((SECONDS + 300))
  while [ "$SECONDS" -lt "$deadline" ]; do
    state="$(app_state "$app")" || return 1
    [ "$state" != "$target" ] || return 0
    sleep 2
  done
  echo "Timed out waiting for $app to become $target (last state: $state)." >&2
  return 1
}

upgrade_preserving_state() {
  local app="$1" state rc=0
  state="$(app_state "$app")" || return 1
  echo "Initial state: $state"
  case "$state" in
    STOPPED)
      # Register before starting: a failed start can still leave containers running.
      RESTORE_APP="$app"
      if ! midclt call --job app.start "$app"; then
        echo "Startup failed; upgrade skipped." >&2
        rc=1
      elif ! wait_app_state "$app" RUNNING; then
        echo "App did not reach RUNNING; upgrade skipped." >&2
        rc=1
      fi
      ;;
    RUNNING) ;;
    *)
      echo "Upgrade skipped: app is $state; expected RUNNING or STOPPED." >&2
      return 1
      ;;
  esac

  if [ "$rc" -eq 0 ]; then
    midclt call --job app.upgrade "$app" \
      '{"app_version":"latest","snapshot_hostpaths":false}' || rc=1
  fi

  if [ -n "$RESTORE_APP" ]; then
    # Always restore, even after failed startup or upgrade.
    if midclt call --job app.stop "$app" && wait_app_state "$app" STOPPED; then
      RESTORE_APP=""
      echo "Original STOPPED state restored."
    else
      echo "ERROR: Could not restore STOPPED state for $app." >&2
      # Retain RESTORE_APP for one final attempt by the EXIT trap.
      return 2
    fi
  fi
  return "$rc"
}

# Refresh the TrueNAS application catalogue before checking for updates.
midclt call --job catalog.sync >/dev/null 2>&1 || true

UPDATES="$(
  midclt call app.query \
    '[["upgrade_available","=",true]]'
)"

if ! jq -e 'type == "array"' >/dev/null 2>&1 <<<"$UPDATES"; then
  echo "TrueNAS returned an invalid response to app.query." >&2
  exit 1
fi

UPDATE_COUNT="$(jq 'length' <<<"$UPDATES")"

# Include custom applications deployed since the last successful report. This
# reports an already installed change; it does not redeploy it a second time.
CHANGED_CUSTOM="$(python3 "$HELPER" changed)" || CHANGED_CUSTOM='[]'
if jq -e 'length > 0' >/dev/null <<<"$CHANGED_CUSTOM"; then
  # Keep the inventory out of command arguments: a populated NAS can exceed
  # Linux's per-argument size limit even when only one app changed.
  printf '%s\n' "$UPDATES" >"$RUN_METADATA/pending.json"
  CHANGED_FILTER="$(jq -cn --argjson ids "$CHANGED_CUSTOM" '[["id","in",$ids]]')" || exit 1
  midclt call app.query "$CHANGED_FILTER" >"$RUN_METADATA/changed.json" || exit 1
  UPDATES="$(jq -s 'add | unique_by(.id)' "$RUN_METADATA/pending.json" "$RUN_METADATA/changed.json")" || exit 1
fi
if ! jq -e 'type == "array"' >/dev/null 2>&1 <<<"$UPDATES"; then
  echo "Could not assemble a valid list of updates and deployed changes." >&2
  exit 1
fi
UPDATE_COUNT="$(jq 'length' <<<"$UPDATES")"

# Do not send an email when no updates are available.
if [ "$UPDATE_COUNT" -eq 0 ]; then
  exit 0
fi

{
  echo "# TrueNAS app update report"
  echo
  echo "**Date:** $(date '+%d %B %Y at %H:%M:%S')"
  echo
  echo "**Updates found:** $UPDATE_COUNT"
  echo
} >"$REPORT_FILE"

SUCCESS_COUNT=0
FAILURE_COUNT=0

while IFS= read -r APP_JSON; do
  APP_ID="$(jq -r '.id' <<<"$APP_JSON")"

  CUSTOM=false
  if is_custom_app "$APP_JSON"; then
    CUSTOM=true
    capture_custom "$APP_ID" "$RUN_METADATA/$APP_ID.before.json"
    # Prefer the last successfully emailed baseline, so manual deployments are
    # covered too. First-time apps use their observed pre-update state.
    if [ -f "$HELPER_DIR/last-reported-custom-apps.json" ] && \
       jq -e --arg app "$APP_ID" 'has($app)' "$HELPER_DIR/last-reported-custom-apps.json" >/dev/null; then
      jq --arg app "$APP_ID" '.[$app]' "$HELPER_DIR/last-reported-custom-apps.json" >"$RUN_METADATA/$APP_ID.before.json"
    fi
  fi

  APP_NAME="$(
    jq -r '
      .metadata.title //
      .name //
      .id
    ' <<<"$APP_JSON"
  )"

  FROM_VERSION="$(
    jq -r '
      .human_version //
      .version //
      "Unknown"
    ' <<<"$APP_JSON"
  )"

  SUMMARY="$(
    midclt call app.upgrade_summary \
      "$APP_ID" \
      '{"app_version":"latest"}' 2>/dev/null
  )"

  if [ "$CUSTOM" = true ]; then
    EXPECTED_VERSION="$(jq -r '.upgrade_human_version // .latest_human_version // "unchanged"' <<<"${SUMMARY:-null}" 2>/dev/null || echo unchanged)"
    CHANGELOG="Custom application notes are resolved from observed deployed versions below."
  elif [ -n "$SUMMARY" ] &&
     jq -e 'type == "object"' >/dev/null 2>&1 <<<"$SUMMARY"; then
    EXPECTED_VERSION="$(
      jq -r '
        .upgrade_human_version //
        .latest_human_version //
        "Unknown"
      ' <<<"$SUMMARY"
    )"

    CHANGELOG="$(
      get_relevant_changelog "$APP_JSON" "$SUMMARY"
    )"
  else
    EXPECTED_VERSION="Unknown"

    CHANGELOG_URL="$(
      jq -r '.metadata.changelog_url // empty' <<<"$APP_JSON"
    )"

    if [ -n "$CHANGELOG_URL" ]; then
      CHANGELOG="The upgrade summary could not be retrieved.

[View full upstream release history]($CHANGELOG_URL)"
    else
      CHANGELOG="The upgrade summary could not be retrieved, and no upstream release-history URL was supplied."
    fi
  fi

  {
    echo "## $APP_NAME"
    echo
    echo "- **Application ID:** $APP_ID"
    echo "- **From:** $FROM_VERSION"
    echo "- **Expected target:** $EXPECTED_VERSION"
    echo
  } >>"$REPORT_FILE"

  # Upgrade the application and wait for the TrueNAS job to complete.
  if { if jq -e '.upgrade_available == true' >/dev/null <<<"$APP_JSON"; then
         upgrade_preserving_state "$APP_ID"
       else
         echo "Reporting a deployment since the last email; no update requested."
       fi; } >"$ERROR_FILE" 2>&1; then

    RESULT="$(
      midclt call app.get_instance "$APP_ID" 2>/dev/null || true
    )"

    TO_VERSION="$(
      jq -r '
        .human_version //
        .version //
        "Unknown"
      ' <<<"${RESULT:-null}"
    )"

    if [ "$CUSTOM" = true ]; then
      capture_custom "$APP_ID" "$RUN_METADATA/$APP_ID.after.json"
      CHANGELOG="$(python3 "$HELPER" report "$RUN_METADATA/$APP_ID.before.json" "$RUN_METADATA/$APP_ID.after.json")" || \
        CHANGELOG="Custom release-note lookup failed; inspect the reporting helper."
      if jq -e '.services | length > 0' "$RUN_METADATA/$APP_ID.after.json" >/dev/null; then
        printf '%s\n' "$APP_ID" >>"$SUCCESS_APPS"
      fi
    fi

    {
      if jq -e '.upgrade_available == true' >/dev/null <<<"$APP_JSON"; then
        echo "- **Result:** Update command completed successfully"
      else
        echo "- **Result:** Previously deployed change detected; no additional restart"
      fi
      echo "- **Installed version:** $TO_VERSION"
      if jq -e '.upgrade_available == true' >/dev/null <<<"${RESULT:-null}"; then
        echo "- **Update status:** TrueNAS still reports an available image update; command success does not prove the image changed."
      fi
      if grep -q 'Original STOPPED state restored.' "$ERROR_FILE"; then
        echo "- **App state:** Temporarily started, upgraded, then stopped again"
      fi
      echo
      echo "### Relevant changes"
      echo
      printf '%s\n' "$CHANGELOG"
      echo
    } >>"$REPORT_FILE"

    SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
  else
    ERROR_TEXT="$(clean_job_error "$ERROR_FILE")"
    if [ "$CUSTOM" = true ]; then
      capture_custom "$APP_ID" "$RUN_METADATA/$APP_ID.after.json"
      CHANGELOG="$(python3 "$HELPER" report "$RUN_METADATA/$APP_ID.before.json" "$RUN_METADATA/$APP_ID.after.json")" || \
        CHANGELOG="Custom release-note lookup failed; the update also failed."
    fi

    {
      echo "- **Result:** Update or state restoration failed"
      echo "- **Version before attempt:** $FROM_VERSION"
      echo
      echo "### Error"
      echo

      if [ -n "$ERROR_TEXT" ]; then
        printf '%s\n' "$ERROR_TEXT"
      else
        echo "No error details were returned."
      fi

      echo
      echo "### Intended changes"
      echo
      printf '%s\n' "$CHANGELOG"
      echo
    } >>"$REPORT_FILE"

    FAILURE_COUNT=$((FAILURE_COUNT + 1))
  fi

  if [ -n "$RESTORE_APP" ]; then
    echo "Further updates halted because $RESTORE_APP could not be stopped." >>"$REPORT_FILE"
    break
  fi

  echo "---" >>"$REPORT_FILE"
  echo >>"$REPORT_FILE"
done < <(jq -c '.[]' <<<"$UPDATES")

{
  echo "## Summary"
  echo
  echo "- **Successful:** $SUCCESS_COUNT"
  echo "- **Failed:** $FAILURE_COUNT"
} >>"$REPORT_FILE"

SUBJECT="TrueNAS apps: $SUCCESS_COUNT updated, $FAILURE_COUNT failed"

MAIL_JSON="$(
  jq -n \
    --arg subject "$SUBJECT" \
    --rawfile text "$REPORT_FILE" \
    '{
      subject: $subject,
      text: $text
    }'
)"

# Supply an explicit sanitized HTML part alongside the plain-text report.
MAIL_JSON="$(python3 "$HELPER" mail "$SUBJECT" "$REPORT_FILE")" || exit 1
if midclt call --job mail.send "$MAIL_JSON" >/dev/null; then
  install -m 600 "$REPORT_FILE" "$LAST_REPORT"
  while IFS= read -r reported_app; do
    python3 "$HELPER" commit "$reported_app" "$RUN_METADATA/$reported_app.after.json" || exit 1
  done <"$SUCCESS_APPS"
else
  exit 1
fi
