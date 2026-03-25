#!/usr/bin/env bash
# ============================================================================
# run_wiki_gen.sh — Wiki regeneration via Copilot CLI with Phase 1 caching
#
# Usage:
#   bash run_wiki_gen.sh [options]
#
# Options:
#   -s, --source DIR        Source directory to document (required or via env)
#   -o, --output DIR        Output base directory (default: /mnt/disk1/zy/internal_wiki)
#   -m, --model MODEL       LLM model name (default: claude-opus-4.6)
#   -n, --name NAME         Project slug for output dir (default: derived from source)
#   --no-cache              Force Phase 1 re-research (ignore cache)
#   --cache-only            Run Phase 1 research only, then stop (populate cache)
#   --max-continues N       Max autopilot continues (default: 50)
#   --keep-snapshots N      Number of old wiki snapshots to keep (default: 7)
#   --log-retention N       Days to keep log files (default: 30)
#   --dry-run               Print plan and exit without running Copilot
#   -h, --help              Show this help message
#
# Environment variables (override defaults, flags take priority):
#   WIKI_SOURCE_DIR         Source directory
#   WIKI_OUTPUT_BASE        Output base directory
#   WIKI_MODEL              LLM model
#   WIKI_SKILL_REPO         Skill repository path
#   WIKI_LOG_DIR            Log directory
#
# Cron entry (daily midnight):
#   0 0 * * * /path/to/run_wiki_gen.sh -s /path/to/source
# ============================================================================
set -euo pipefail

# === Defaults (environment overrides, flags override both) ===
SKILL_REPO="${WIKI_SKILL_REPO:-/mnt/disk1/zy/stock_related/finicial_plugin}"
SOURCE_DIR="${WIKI_SOURCE_DIR:-/mnt/disk2/applications.simulators.cpu.keiko/indigo}"
OUTPUT_BASE="${WIKI_OUTPUT_BASE:-/mnt/disk1/zy/internal_wiki}"
LOG_DIR="${WIKI_LOG_DIR:-/mnt/disk1/zy/copilot_cli/logs}"
MODEL="${WIKI_MODEL:-claude-opus-4.6}"
PROJECT_NAME=""
MAX_CONTINUES=50
KEEP_SNAPSHOTS=7
LOG_RETENTION_DAYS=30
NO_CACHE=false
CACHE_ONLY=false
DRY_RUN=false

# === Parse arguments ===
usage() {
  sed -n '2,/^# ====/s/^# \?//p' "$0"
  exit 0
}

while [ $# -gt 0 ]; do
  case "$1" in
    -s|--source)       SOURCE_DIR="$2"; shift 2 ;;
    -o|--output)       OUTPUT_BASE="$2"; shift 2 ;;
    -m|--model)        MODEL="$2"; shift 2 ;;
    -n|--name)         PROJECT_NAME="$2"; shift 2 ;;
    --no-cache)        NO_CACHE=true; shift ;;
    --cache-only)      CACHE_ONLY=true; shift ;;
    --max-continues)   MAX_CONTINUES="$2"; shift 2 ;;
    --keep-snapshots)  KEEP_SNAPSHOTS="$2"; shift 2 ;;
    --log-retention)   LOG_RETENTION_DAYS="$2"; shift 2 ;;
    --dry-run)         DRY_RUN=true; shift ;;
    -h|--help)         usage ;;
    *)                 echo "[ERROR] Unknown option: $1" >&2; exit 1 ;;
  esac
done

# === Resolve source (required) ===
if [ -z "$SOURCE_DIR" ]; then
  echo "[ERROR] Source directory required. Use -s/--source or set WIKI_SOURCE_DIR." >&2
  exit 1
fi
SOURCE_DIR="$(realpath "$SOURCE_DIR")"

# === Derive project name from source dir if not given ===
if [ -z "$PROJECT_NAME" ]; then
  PROJECT_NAME="$(basename "$SOURCE_DIR" | tr '[:upper:]' '[:lower:]' | tr ' .' '_')"
fi

# === Environment (cron has minimal PATH) ===
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
if [ -s "$NVM_DIR/nvm.sh" ]; then . "$NVM_DIR/nvm.sh"; fi
export PATH="$HOME/.local/bin:$PATH"

# === Locate copilot binary ===
COPILOT_BIN="$(command -v copilot 2>/dev/null || true)"
if [ -z "$COPILOT_BIN" ]; then
  echo "[ERROR] copilot binary not found in PATH" >&2
  exit 1
fi

# === Pre-flight checks ===
SCRIPTS_DIR="$SKILL_REPO/.github/skills/wiki-generator/scripts"

if [ ! -d "$SKILL_REPO/.github/skills/wiki-generator" ]; then
  echo "[ERROR] wiki-generator skill not found at $SKILL_REPO" >&2
  exit 1
fi

if [ ! -d "$SOURCE_DIR" ]; then
  echo "[ERROR] Source directory not found: $SOURCE_DIR" >&2
  exit 1
fi

# === Timestamps & paths ===
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUTPUT_DIR="${OUTPUT_BASE}/${PROJECT_NAME}_${TIMESTAMP}"
LOG_FILE="${LOG_DIR}/wiki_gen_${PROJECT_NAME}_${TIMESTAMP}.log"

# === Phase 1 cache check ===
# Look for the most recent output that has a _research/_manifest.json
CACHE_DIR=""
CACHE_STATUS="MISS"

find_latest_cache() {
  _pattern="${OUTPUT_BASE}/${PROJECT_NAME}_*"
  for dir in $(ls -dt $_pattern 2>/dev/null); do
    if [ -f "$dir/docs/_research/_manifest.json" ]; then
      echo "$dir/docs"
      return 0
    fi
  done
  return 1
}

if [ "$NO_CACHE" = "false" ]; then
  CACHE_DIR="$(find_latest_cache || true)"
  if [ -n "$CACHE_DIR" ]; then
    CACHE_STATUS="$(bash "$SCRIPTS_DIR/check-cache.sh" "$SOURCE_DIR" "$CACHE_DIR" 2>/dev/null | head -1 || echo "MISS")"
  fi
fi

CACHE_HIT=false
case "$CACHE_STATUS" in
  HIT*) CACHE_HIT=true ;;
esac

# === Build the prompt ===
PROMPT="Use the wiki-generator skill to generate a complete HTML wiki for the source code at ${SOURCE_DIR}. Save all generated HTML files to ${OUTPUT_DIR}."

if [ "$CACHE_HIT" = "true" ]; then
  PROMPT="${PROMPT} Phase 1 research cache is FRESH at ${CACHE_DIR}/_research/. Copy the _research/ directory to the new output, then skip Phase 1 and start from Phase 1.5."
elif [ "$NO_CACHE" = "true" ]; then
  PROMPT="${PROMPT} Force a full Phase 1 re-research (ignore any cached data)."
fi

if [ "$CACHE_ONLY" = "true" ]; then
  PROMPT="Use the wiki-generator skill Phase 1 ONLY: research the source code at ${SOURCE_DIR}, save research cache to ${OUTPUT_DIR}/docs/_research/, then STOP. Do not generate any HTML pages."
fi

# === Dry-run output ===
if [ "$DRY_RUN" = "true" ]; then
  echo "=== Wiki Generation Plan ==="
  echo "Source:       $SOURCE_DIR"
  echo "Output:       $OUTPUT_DIR"
  echo "Project:      $PROJECT_NAME"
  echo "Model:        $MODEL"
  echo "Max continues:$MAX_CONTINUES"
  echo "Cache status: $CACHE_STATUS"
  echo "Cache dir:    ${CACHE_DIR:-none}"
  echo "Cache hit:    $CACHE_HIT"
  echo "No-cache:     $NO_CACHE"
  echo "Cache-only:   $CACHE_ONLY"
  echo "Copilot:      $COPILOT_BIN"
  echo "Skill repo:   $SKILL_REPO"
  echo "Log file:     $LOG_FILE"
  echo ""
  echo "Prompt:"
  echo "  $PROMPT"
  exit 0
fi

# === Setup output and log directories ===
mkdir -p "$OUTPUT_DIR/docs" "$LOG_DIR"

# === Copy cached research if cache hit ===
if [ "$CACHE_HIT" = "true" ] && [ -d "$CACHE_DIR/_research" ]; then
  mkdir -p "$OUTPUT_DIR/docs/_research"
  cp -a "$CACHE_DIR/_research/." "$OUTPUT_DIR/docs/_research/"
  echo "[$(date -Iseconds)] Copied cached research from $CACHE_DIR/_research/" >> "$LOG_FILE"
fi

# === Log header ===
{
  echo "[$(date -Iseconds)] Wiki generation started"
  echo "  Source:      $SOURCE_DIR"
  echo "  Output:      $OUTPUT_DIR"
  echo "  Project:     $PROJECT_NAME"
  echo "  Model:       $MODEL"
  echo "  Cache:       $CACHE_STATUS"
  echo "  Cache dir:   ${CACHE_DIR:-none}"
  echo "  No-cache:    $NO_CACHE"
  echo "  Cache-only:  $CACHE_ONLY"
  echo "  Copilot:     $COPILOT_BIN"
  echo "---"
} >> "$LOG_FILE"

# === Run Copilot ===
cd "$SKILL_REPO"

"$COPILOT_BIN" -p \
  "$PROMPT" \
  --allow-all \
  --autopilot \
  --max-autopilot-continues "$MAX_CONTINUES" \
  --model "$MODEL" \
  >> "$LOG_FILE" 2>&1

EXIT_CODE=$?

{
  echo "---"
  echo "[$(date -Iseconds)] Wiki generation finished (exit code: $EXIT_CODE)"
} >> "$LOG_FILE"

# === Log rotation ===
find "$LOG_DIR" -name "wiki_gen_*.log" -mtime +"$LOG_RETENTION_DAYS" -delete 2>/dev/null || true

# === Prune old wiki snapshots ===
if [ "$KEEP_SNAPSHOTS" -gt 0 ]; then
  ls -dt "${OUTPUT_BASE}/${PROJECT_NAME}_"* 2>/dev/null \
    | tail -n +"$((KEEP_SNAPSHOTS + 1))" \
    | xargs rm -rf 2>/dev/null || true
fi

# === Summary ===
if [ $EXIT_CODE -eq 0 ]; then
  PAGE_COUNT=$(find "$OUTPUT_DIR" -name '*.html' 2>/dev/null | wc -l)
  echo "[OK] Wiki generated: $OUTPUT_DIR ($PAGE_COUNT pages)"
else
  echo "[FAIL] Wiki generation failed (exit $EXIT_CODE). See $LOG_FILE" >&2
fi

exit $EXIT_CODE
