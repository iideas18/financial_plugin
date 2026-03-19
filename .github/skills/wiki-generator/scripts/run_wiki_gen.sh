#!/usr/bin/env bash
# ============================================================================
# run_wiki_gen.sh — Nightly wiki regeneration via Copilot CLI
#
# Cron entry (daily midnight):
#   0 0 * * * /mnt/disk1/zy/copilot_cli/run_wiki_gen.sh
# ============================================================================
set -euo pipefail

# === Environment (cron has minimal PATH) ===
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
export PATH="$HOME/.local/bin:$PATH"

# === Configuration ===
COPILOT_BIN="$(command -v copilot)"
SKILL_REPO="/mnt/disk1/zy/stock_related/finicial_plugin"
SOURCE_DIR="/mnt/disk1/zy/copilot-api"
OUTPUT_BASE="/mnt/disk1/zy/internal_wiki"
LOG_DIR="/mnt/disk1/zy/copilot_cli/logs"
MODEL="claude-opus-4.6"
MAX_CONTINUES=50
LOG_RETENTION_DAYS=30

# === Derived variables ===
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUTPUT_DIR="${OUTPUT_BASE}/copilot_api_${TIMESTAMP}"
LOG_FILE="${LOG_DIR}/wiki_gen_${TIMESTAMP}.log"

# === Pre-flight checks ===
if [ -z "$COPILOT_BIN" ]; then
  echo "[ERROR] copilot binary not found in PATH" >&2
  exit 1
fi

if [ ! -d "$SKILL_REPO/.github/skills/wiki-generator" ]; then
  echo "[ERROR] wiki-generator skill not found at $SKILL_REPO" >&2
  exit 1
fi

if [ ! -d "$SOURCE_DIR" ]; then
  echo "[ERROR] Source directory not found: $SOURCE_DIR" >&2
  exit 1
fi

# === Setup output and log directories ===
mkdir -p "$OUTPUT_DIR" "$LOG_DIR"

echo "[$(date -Iseconds)] Wiki generation started" >> "$LOG_FILE"
echo "  Source:  $SOURCE_DIR" >> "$LOG_FILE"
echo "  Output:  $OUTPUT_DIR" >> "$LOG_FILE"
echo "  Model:   $MODEL" >> "$LOG_FILE"
echo "  Copilot: $COPILOT_BIN" >> "$LOG_FILE"
echo "---" >> "$LOG_FILE"

# === Run Copilot with wiki-generator skill ===
cd "$SKILL_REPO"

"$COPILOT_BIN" -p \
  "Use the wiki-generator skill to generate a complete HTML wiki for the source code at ${SOURCE_DIR}. Save all generated HTML files to ${OUTPUT_DIR}." \
  --allow-all \
  --autopilot \
  --max-autopilot-continues "$MAX_CONTINUES" \
  --model "$MODEL" \
  >> "$LOG_FILE" 2>&1

EXIT_CODE=$?

echo "---" >> "$LOG_FILE"
echo "[$(date -Iseconds)] Wiki generation finished (exit code: $EXIT_CODE)" >> "$LOG_FILE"

# === Log rotation (keep last N days) ===
find "$LOG_DIR" -name "wiki_gen_*.log" -mtime +${LOG_RETENTION_DAYS} -delete 2>/dev/null || true

# === Optional: clean up old wiki snapshots (keep last 7) ===
# Uncomment the following lines to auto-prune old wiki outputs:
# ls -dt "${OUTPUT_BASE}"/copilot_api_* 2>/dev/null | tail -n +8 | xargs rm -rf 2>/dev/null || true

exit $EXIT_CODE
