#!/usr/bin/env bash
# ============================================================
# copy_to__home.sh
#
# Copies the directories listed in COPY_DIRS (config.sh) from
#   $DATA_BASE   (scratch)
# to BOTH
#   $_PROJECTS_BASE
#   $PROJECTS_BASE
#
# Uses rsync, so it is safe to stop and re-run: files already
# copied are skipped, half-copied files are resumed.
#
# For each directory/destination it:
#   1. does a dry run to work out how much is left to copy
#   2. checks the destination has enough free space (skips if not)
#   3. copies
#   4. re-runs a dry run to verify nothing is left uncopied
#
# Outputs (in $COPY_LOG_DIR):
#   copy_<YYYYmmdd_HHMMSS>.log          main timestamped log + summary
#   copy_<YYYYmmdd_HHMMSS>_files.log    one line per file transferred
#   copy_ledger.csv                     one row per dir/destination per run,
#                                       so "total files moved" accumulates
#                                       across re-runs
#
# Usage:
#   ./copy_to__home.sh --dry-run    # report sizes/space only, copy nothing
#   ./copy_to__home.sh              # do the copy
#
# Submit as a batch job (recommended, keeps it off the head node):
#   sbatch copy_to__home.sh --dry-run    # check sizes/space first
#   sbatch copy_to__home.sh              # the real copy
# It also still runs directly (./copy_to__home.sh) if you prefer.
#
# Optional: throttle I/O on the shared filesystem, e.g.
#   RSYNC_EXTRA_OPTS="--bwlimit=100M" sbatch --export=ALL copy_to__home.sh
# ============================================================

# ---- Slurm resources (ignored when run directly) ----------
# rsync is single-threaded and light on RAM, and the job is I/O-bound.
# EDIT partition/time to suit your cluster; --time must not exceed the
# partition's limit. If the job times out, just re-submit: rsync resumes.
#SBATCH --job-name=copy_files
#SBATCH --output=copy__home_%j.out
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=12:00:00
#SBATCH --partition=Short

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Under sbatch, Slurm runs a COPY of this script from a spool directory, so
# $SCRIPT_DIR no longer points at your scripts folder. Look in several places.
CONFIG_FILE="${CONFIG_FILE:-$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments/config.sh}"


DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run|-n) DRY_RUN=1 ;;
    -h|--help)    awk 'NR>1 && /^#/ {print; next} NR>1 {exit}' "$0"; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

[[ -n "$CONFIG_FILE" && -f "$CONFIG_FILE" ]] || { echo "ERROR: config.sh not found. Set CONFIG_FILE=/path/to/config.sh" >&2; exit 2; }
# shellcheck source=/dev/null
source "$CONFIG_FILE"

for v in DATA_BASE _PROJECTS_BASE PROJECTS_BASE COPY_DIRS COPY_LOG_DIR; do
  [[ -n "${!v:-}" ]] || { echo "ERROR: $v is not set in $CONFIG_FILE" >&2; exit 2; }
done

IFS=',' read -ra DIRS <<< "$COPY_DIRS"
DESTS=("$_PROJECTS_BASE" "$PROJECTS_BASE")

# ---------- logging ----------
mkdir -p "$COPY_LOG_DIR" || { echo "ERROR: cannot create $COPY_LOG_DIR" >&2; exit 2; }
RUN_TS="$(date +%Y%m%d_%H%M%S)"
LOG="$COPY_LOG_DIR/copy_${RUN_TS}.log"
FILE_LOG="$COPY_LOG_DIR/copy_${RUN_TS}_files.log"
LEDGER="$COPY_LOG_DIR/copy_ledger.csv"
# Scratch space for rsync output. Kept inside the log dir (known to be writable)
# rather than $TMPDIR, which can be unset/nonexistent on compute nodes. Never
# continue with an empty $TMP: "$TMP/dry.txt" would silently become "/dry.txt".
TMP="$(mktemp -d "$COPY_LOG_DIR/.tmp_${RUN_TS}_XXXXXX")"
[[ -n "$TMP" && -d "$TMP" && -w "$TMP" ]] || { echo "ERROR: cannot create a temp dir under $COPY_LOG_DIR" >&2; exit 2; }

# NOTE: deliberately no `exec > >(tee ...)`. If Slurm signals the whole job the tee
# dies first, and the next log line would SIGPIPE-kill this script before it could
# record what had been transferred. Instead each line is appended to $LOG directly.
trap '' PIPE

ts()  { date '+%Y-%m-%d %H:%M:%S'; }
log() {
  local line; line="$(printf '[%s] %s' "$(ts)" "$*")"
  echo "$line" 2>/dev/null
  echo "$line" >> "$LOG"
}
hr()  { numfmt --to=iec --format='%.2f' "${1:-0}" 2>/dev/null || echo "${1:-0}"; }

# Pull a number out of an rsync --stats line, e.g.
#   "Number of regular files transferred: 1,200"  ->  1200
stat_num() {
  local n
  n="$(grep -E "$2" "$1" | head -n1 | sed -E 's/^[^:]+:[[:space:]]*//; s/[[:space:]].*//' | tr -d ',')"
  echo "${n:-0}"
}

# --no-perms matters: with -p, rsync copies the SOURCE directory mode onto destination
# directories, which strips the setgid bit. Project dirs rely on setgid so that new files
# inherit the project GROUP (and are charged to its quota); without it, files fall back to
# your primary group and hit that group's (much smaller) quota. See also the mkdir
# pre-creation step in process().
RSYNC_OPTS=(-a --no-owner --no-group --no-perms --stats --partial --partial-dir=.rsync-partial)
if [[ -n "${RSYNC_EXTRA_OPTS:-}" ]]; then
  read -ra EXTRA_OPTS <<< "$RSYNC_EXTRA_OPTS"
  RSYNC_OPTS+=("${EXTRA_OPTS[@]}")
fi
FILES_RE='^Number of (regular )?files transferred'
BYTES_RE='^Total transferred file size'
SRC_RE='^Number of files'

TOTAL_FILES=0
TOTAL_BYTES=0
N_FAILED=0
N_SKIPPED=0
N_OK=0
START_SECONDS=$SECONDS

# ---- Space checks -------------------------------------------------------
# `df` reports the free space of the WHOLE filesystem, which on shared Lustre is
# usually far more than your group/user quota allows. So we take the lowest of:
# df free space, the group quota remaining, and the user quota remaining.
AVAIL=0

# quota_check <-g|-u> <id> <path> <label>: lowers $AVAIL if a quota is tighter.
# Silently skipped (df only) if lfs is missing, errors, or the output can't be parsed.
quota_check() {
  local kind="$1" id="$2" path="$3" label="$4" out used soft hard lim left
  command -v lfs >/dev/null 2>&1 || return 0
  out="$(lfs quota -q "$kind" "$id" "$path" 2>/dev/null)" || return 0
  # Output is "fs kbytes quota limit grace files quota limit grace"; a long fs name
  # wraps onto its own line and a '*' marks an exceeded quota. Join lines, drop '*',
  # and take the first purely numeric token as "used".
  read -r used soft hard < <(echo "$out" | tr -d '*' | tr '\n' ' ' \
      | awk '{for(i=1;i<=NF;i++) if ($i ~ /^[0-9]+$/) {print $i, $(i+1), $(i+2); exit}}')
  if [[ ! "${used:-}" =~ ^[0-9]+$ || ! "${soft:-}" =~ ^[0-9]+$ || ! "${hard:-}" =~ ^[0-9]+$ ]]; then
    log "  $label quota: could not parse 'lfs quota' output, ignoring it"; return 0
  fi
  lim=$(( soft > 0 ? soft : hard ))      # soft quota is the safer limit to plan against
  if (( lim == 0 )); then
    log "  $label quota: none set (currently using $(hr $(( used * 1024 ))))"; return 0
  fi
  left=$(( (lim - used) * 1024 )); (( left < 0 )) && left=0
  log "  $label quota: using $(hr $(( used * 1024 ))) of $(hr $(( lim * 1024 ))) (hard limit $(hr $(( hard * 1024 )))) -> $(hr "$left") left"
  (( left < AVAIL )) && AVAIL=$left
  return 0
}

# compute_avail <existing path>: sets $AVAIL to the usable space for new files there.
# new_file_gid <dir>: the group that new files created in <dir> will belong to
# (the directory's own group if it is setgid, otherwise your primary group).
new_file_gid() {
  local mode gid
  gid="$(stat -c %g "$1" 2>/dev/null)"; mode="$(stat -c %a "$1" 2>/dev/null || echo 0)"
  if [[ -n "$gid" ]] && (( 8#$mode & 8#2000 )); then echo "$gid"; else id -g; fi
}
gname_of() { getent group "$1" 2>/dev/null | cut -d: -f1; }

# group_guard <dest_base> <dst>: refuse to copy if files in <dst> would end up in a
# different group (=> a different quota) than files created directly in <dest_base>.
group_guard() {
  local want got
  want="$(new_file_gid "$1")"; got="$(new_file_gid "$2")"
  [[ "$want" == "$got" ]] && return 0
  log "FAILED: files copied into $2 would belong to group ${got} ($(gname_of "$got")),"
  log "        but files in $1 belong to group ${want} ($(gname_of "$want")): they'd be charged to the wrong quota."
  log "        Most likely $2 lost its setgid bit (e.g. from an earlier rsync -a)."
  log "        Fix: delete $2 if it only holds a partial copy and re-run, or run: chmod g+s $2"
  return 1
}

compute_avail() {
  local p="$1" gid gname
  AVAIL="$(df -B1 --output=avail "$p" | tail -n1 | tr -d ' ')"
  [[ "$AVAIL" =~ ^[0-9]+$ ]] || AVAIL=0
  log "  filesystem free (df, ignores quotas): $(hr "$AVAIL")"
  # New files are charged to the directory's group if it is setgid, else to your primary group
  gid="$(new_file_gid "$p")"
  gname="$(gname_of "$gid")"
  quota_check -g "$gid" "$p" "group ${gname:-$gid}"
  quota_check -u "$(id -u)" "$p" "user $(id -un)"
}

# Log rsync's error output. Prefers lines that look like errors, but falls back to
# the raw output so a message in an unexpected format is never hidden.
show_errors() {  # file n
  local out
  out="$(grep -iE '^rsync|error|denied|no space|failed|quota|unknown|invalid|usage' "$1" | head -n "$2")"
  [[ -n "$out" ]] || out="$(head -n "$2" "$1")"
  [[ -n "$out" ]] || out="(rsync printed nothing)"
  while IFS= read -r l; do log "    $l"; done <<< "$out"
}

# State of the copy currently in progress (used if we get interrupted)
CUR_DEST=""; CUR_DIR=""; CUR_LINE0=0; CUR_T0=0

# Files/bytes transferred since line $1 of the per-file log. Used when rsync is
# killed (e.g. Slurm time limit) and never got to print its own --stats.
filelog_counts() {
  tail -n +"$(( $1 + 1 ))" "$FILE_LOG" 2>/dev/null \
    | awk '$4 ~ /^>f/ {n++; b+=$NF} END {print n+0, b+0}'
}

ledger_add() {  # dest dir status files bytes elapsed
  [[ $DRY_RUN -eq 1 ]] && return
  [[ -f "$LEDGER" ]] || echo "timestamp,destination,directory,status,files_moved,bytes_moved,elapsed_s" > "$LEDGER"
  printf '%s,%s,%s,%s,%s,%s,%s\n' "$(ts)" "$1" "$2" "$3" "$4" "$5" "$6" >> "$LEDGER"
}

summary() {
  log "==================== SUMMARY ===================="
  log "This run    : ${TOTAL_FILES} files moved, ${TOTAL_BYTES} bytes ($(hr "$TOTAL_BYTES"))"
  log "Jobs        : ${N_OK} ok, ${N_SKIPPED} skipped, ${N_FAILED} failed"
  log "Elapsed     : $(( SECONDS - START_SECONDS )) s"
  if [[ $DRY_RUN -eq 0 && -f "$LEDGER" ]]; then
    read -r cf cb < <(awk -F, 'NR>1 {f+=$5; b+=$6} END {print f+0, b+0}' "$LEDGER")
    log "All runs    : ${cf} files moved in total, ${cb} bytes ($(hr "$cb"))  [from $LEDGER]"
  fi
  log "Main log    : $LOG"
  [[ $DRY_RUN -eq 1 ]] || log "File list   : $FILE_LOG"
}

on_signal() {
  log "INTERRUPTED (signal or Slurm time limit). rsync is resumable: just re-run/re-submit."
  if [[ -n "$CUR_DIR" ]]; then
    local f b
    read -r f b < <(filelog_counts "$CUR_LINE0")
    TOTAL_FILES=$((TOTAL_FILES + f)); TOTAL_BYTES=$((TOTAL_BYTES + b))
    log "Before the interruption, $CUR_DIR -> $CUR_DEST had $f files, $b bytes transferred (from file log)"
    ledger_add "$CUR_DEST" "$CUR_DIR" "INTERRUPTED" "$f" "$b" $((SECONDS - CUR_T0))
  fi
  summary
  exit 130
}
trap on_signal INT TERM
trap 'rm -rf "$TMP"' EXIT

process() {  # dest_base dir
  local dest_base="$1" d="$2"
  local src="$DATA_BASE/$d" dst="$dest_base/$d"
  local t0=$SECONDS

  log "---- $d  ->  $dst"

  if [[ ! -d "$src" ]]; then
    log "SKIPPED: source directory does not exist: $src"
    ledger_add "$dest_base" "$d" "SKIPPED_NO_SOURCE" 0 0 0
    N_SKIPPED=$((N_SKIPPED + 1)); return
  fi

  # Nearest existing parent of the destination (the dir itself may not exist yet)
  local p="$dst"
  while [[ ! -e "$p" ]]; do p="$(dirname "$p")"; done

  # Per-destination rsync options. SMB/CIFS shares (e.g. PROJECTS) may store timestamps at
  # coarser precision, which makes rsync see every file as "changed" on each run (and the
  # verify step fail). So for those, treat mtimes within 1 s as equal. (Permissions are
  # never copied, see RSYNC_OPTS.)
  local -a ropts=("${RSYNC_OPTS[@]}")
  local fstype
  # (GNU df refuses to combine -T with --output; use --output=fstype alone, and fall
  # back to stat -f, which reports "smb2"/"cifs" for SMB mounts.)
  fstype="$(df --output=fstype "$p" 2>/dev/null | tail -n1 | tr -d ' ')"
  [[ -n "$fstype" && "$fstype" != "Type" ]] || fstype="$(stat -f -c %T "$p" 2>/dev/null)"
  case "$fstype" in
    cifs|smb*)
      ropts+=(--modify-window=1)
      log "Destination filesystem: $fstype (SMB share) -> adding --modify-window=1" ;;
    *)
      log "Destination filesystem: ${fstype:-unknown}" ;;
  esac

  if [[ -d "$dst" ]]; then
    group_guard "$dest_base" "$dst" || {
      ledger_add "$dest_base" "$d" "FAILED_GROUP" 0 0 $((SECONDS - t0))
      N_FAILED=$((N_FAILED + 1)); return; }
  fi

  # 1. dry run: how much is left to copy?
  rsync "${ropts[@]}" --dry-run "$src/" "$dst/" > "$TMP/dry.txt" 2>&1
  local rc=$?
  if [[ $rc -ne 0 && $rc -ne 24 ]]; then
    log "FAILED: pre-copy dry run exited with code $rc"
    log "  command: rsync ${ropts[*]} --dry-run $src/ $dst/"
    show_errors "$TMP/dry.txt" 10
    ledger_add "$dest_base" "$d" "FAILED_DRYRUN" 0 0 $((SECONDS - t0))
    N_FAILED=$((N_FAILED + 1)); return
  fi
  local src_files need_files need_bytes
  src_files="$(stat_num "$TMP/dry.txt" "$SRC_RE")"
  need_files="$(stat_num "$TMP/dry.txt" "$FILES_RE")"
  need_bytes="$(stat_num "$TMP/dry.txt" "$BYTES_RE")"
  log "Source has $src_files entries; still to copy: $need_files files, $need_bytes bytes ($(hr "$need_bytes"))"

  # 2. free-space AND quota check (on the nearest existing parent, +2% margin)
  local required
  log "Space available at $p:"
  compute_avail "$p"
  required=$(( need_bytes + need_bytes / 50 ))
  log "Usable space (lowest of the above): $(hr "$AVAIL") ; required (incl. 2% margin): $(hr "$required")"
  if (( AVAIL < required )); then
    log "SKIPPED: not enough free space or quota. Free some up or pick a smaller directory."
    ledger_add "$dest_base" "$d" "SKIPPED_NO_SPACE" 0 0 $((SECONDS - t0))
    N_SKIPPED=$((N_SKIPPED + 1)); return
  fi

  if [[ $DRY_RUN -eq 1 ]]; then
    log "DRY RUN: would copy $need_files files ($(hr "$need_bytes")). Nothing copied."
    N_OK=$((N_OK + 1)); return
  fi
  if (( need_files == 0 )); then
    log "Already up to date, nothing to copy."
  fi

  # 3. the copy
  mkdir -p "$dst" || { log "FAILED: cannot create $dst"; N_FAILED=$((N_FAILED + 1)); return; }
  # Pre-create the whole directory tree with plain mkdir. The kernel gives such directories
  # the setgid bit and group of their parent, so files inherit the project group. If rsync
  # created the directories itself it would give them the source's mode (no setgid) and
  # files in every nested subdirectory would fall back to your primary group.
  # (Existing directories are left untouched thanks to --no-perms.)
  ( cd "$src" && find . -type d -print0 ) | ( cd "$dst" && xargs -0 -r mkdir -p -- ) \
    || { log "FAILED: could not pre-create the directory tree under $dst"
         ledger_add "$dest_base" "$d" "FAILED_MKDIR" 0 0 $((SECONDS - t0))
         N_FAILED=$((N_FAILED + 1)); return; }
  group_guard "$dest_base" "$dst" || {
      ledger_add "$dest_base" "$d" "FAILED_GROUP" 0 0 $((SECONDS - t0))
      N_FAILED=$((N_FAILED + 1)); return; }
  echo "=== $(ts)  $src -> $dst ===" >> "$FILE_LOG"
  log "Copying... (progress: tail -f $FILE_LOG)"
  CUR_DEST="$dest_base"; CUR_DIR="$d"; CUR_T0=$t0; CUR_LINE0="$(wc -l < "$FILE_LOG")"
  rsync "${ropts[@]}" --log-file="$FILE_LOG" --log-file-format='%i %n %l' \
        "$src/" "$dst/" > "$TMP/run.txt" 2>&1
  rc=$?
  CUR_DIR=""
  local files bytes
  files="$(stat_num "$TMP/run.txt" "$FILES_RE")"
  bytes="$(stat_num "$TMP/run.txt" "$BYTES_RE")"
  if [[ $rc -ne 0 && $rc -ne 24 ]]; then
    # rsync's stats also count files it tried but failed to copy, so on errors
    # take the numbers from the per-file log, which only lists completed files.
    read -r files bytes < <(filelog_counts "$CUR_LINE0")
  fi
  TOTAL_FILES=$((TOTAL_FILES + files))
  TOTAL_BYTES=$((TOTAL_BYTES + bytes))
  log "rsync exit code $rc ; moved $files files, $bytes bytes ($(hr "$bytes")) in $((SECONDS - t0)) s"
  if [[ $rc -ne 0 && $rc -ne 24 ]]; then
    log "FAILED: rsync reported errors (shown below). Fix the cause, then re-run: rsync resumes."
    show_errors "$TMP/run.txt" 10
    ledger_add "$dest_base" "$d" "FAILED_RSYNC_$rc" "$files" "$bytes" $((SECONDS - t0))
    N_FAILED=$((N_FAILED + 1)); return
  fi

  # 4. verify: a second dry run should find nothing left to transfer
  rsync "${ropts[@]}" --dry-run "$src/" "$dst/" > "$TMP/verify.txt" 2>&1
  local left
  left="$(stat_num "$TMP/verify.txt" "$FILES_RE")"
  case "$fstype" in cifs|smb*) ;; *)
    local wantg badg
    wantg="$(new_file_gid "$dest_base")"
    badg="$(find "$dst" ! -gid "$wantg" -print -quit 2>/dev/null)"
    if [[ -n "$badg" ]]; then
      log "WARNING: found files/dirs NOT in group $wantg ($(gname_of "$wantg")), e.g. $badg"
      log "         They are charged to another group's quota. Check with: find $dst ! -gid $wantg | head"
    else
      log "GROUP CHECK OK: everything under $dst is in group $wantg ($(gname_of "$wantg"))."
    fi ;;
  esac
  if (( left == 0 )); then
    log "VERIFY OK: destination matches source (0 files outstanding)."
    ledger_add "$dest_base" "$d" "OK" "$files" "$bytes" $((SECONDS - t0))
    N_OK=$((N_OK + 1))
  else
    log "VERIFY FAILED: $left files still differ between source and destination."
    ledger_add "$dest_base" "$d" "VERIFY_FAILED" "$files" "$bytes" $((SECONDS - t0))
    N_FAILED=$((N_FAILED + 1))
  fi
}

# ---------- main ----------
log "copy_to__home.sh started$( [[ $DRY_RUN -eq 1 ]] && echo ' (DRY RUN)')"
log "Host         : $(hostname)   User: $(whoami)"
RSYNC_BIN="$(command -v rsync || true)"
[[ -n "$RSYNC_BIN" ]] || { log "ERROR: rsync not found in PATH ($PATH)"; exit 2; }
log "rsync        : $RSYNC_BIN  ($(rsync --version 2>&1 | head -n1))"
log "Slurm job    : ${SLURM_JOB_ID:-not running under Slurm}"
log "Config       : $CONFIG_FILE"
log "Source base  : $DATA_BASE"
log "Destinations : ${DESTS[*]}"
log "Directories  : ${DIRS[*]}"

for d in "${DIRS[@]}"; do
  d="${d//[[:space:]]/}"
  [[ -z "$d" ]] && continue
  for dest in "${DESTS[@]}"; do
    process "$dest" "$d"
  done
done

summary
[[ $N_FAILED -eq 0 ]] || exit 1
exit 0