#!/bin/bash
# Non-destructive installer for ArcadeLED on Batocera (Phase 1).
#
# Safety guarantees:
#   - Never modifies read-only Batocera OS system files.
#   - Never overwrites user custom.sh or existing user configs without backup.
#   - Supports --dry-run and --uninstall.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ARCADELED_HOME="${ARCADELED_HOME:-/userdata/system/arcadeled}"
ES_HOOK_DIR="/userdata/system/configs/emulationstation/scripts/game-selected"
ES_HOOK_FILE="${ES_HOOK_DIR}/arcadeled_game_selected.sh"

DRY_RUN=0
UNINSTALL=0

for arg in "$@"; do
    case "$arg" in
        --dry-run)   DRY_RUN=1 ;;
        --uninstall) UNINSTALL=1 ;;
        -h|--help)
            echo "Usage: $0 [--dry-run] [--uninstall]"
            exit 0
            ;;
        *)
            echo "Unknown option: $arg" >&2
            exit 1
            ;;
    esac
done

run_cmd() {
    if [ "$DRY_RUN" -eq 1 ]; then
        echo "[DRY-RUN] $*"
    else
        "$@"
    fi
}

if [ "$UNINSTALL" -eq 1 ]; then
    echo "Removing ArcadeLED Batocera game-selected hook..."
    if [ -f "${ES_HOOK_FILE}" ]; then
        run_cmd rm -f "${ES_HOOK_FILE}"
        echo "Removed: ${ES_HOOK_FILE}"
    else
        echo "Hook not present: ${ES_HOOK_FILE}"
    fi
    echo "User data in ${ARCADELED_HOME} was preserved (delete manually if no longer needed)."
    exit 0
fi

echo "=== ArcadeLED Batocera Installer (Phase 1) ==="
echo "Source repo : ${REPO_ROOT}"
echo "Install dir : ${ARCADELED_HOME}"
echo "ES hook file: ${ES_HOOK_FILE}"
echo ""

if [ ! -d "/userdata/system" ] && [ "$DRY_RUN" -eq 0 ]; then
    echo "WARNING: /userdata/system not found. Are you running on Batocera?" >&2
    echo "Re-run with --dry-run to preview actions, or set ARCADELED_HOME explicitly." >&2
    exit 1
fi

run_cmd mkdir -p "${ARCADELED_HOME}"
run_cmd mkdir -p "${ARCADELED_HOME}/host/logs"
run_cmd mkdir -p "${ES_HOOK_DIR}"

# Copy host application without overwriting existing user config files if present.
if [ "$DRY_RUN" -eq 1 ]; then
    echo "[DRY-RUN] Copy host/ modules to ${ARCADELED_HOME}/host/"
else
    mkdir -p "${ARCADELED_HOME}/host/core" \
             "${ARCADELED_HOME}/host/transports" \
             "${ARCADELED_HOME}/host/adapters/batocera" \
             "${ARCADELED_HOME}/host/config"

    cp -f "${REPO_ROOT}/host/__init__.py" "${ARCADELED_HOME}/host/"
    cp -f "${REPO_ROOT}/host/main.py" "${ARCADELED_HOME}/host/"
    cp -f "${REPO_ROOT}/host/core/"*.py "${ARCADELED_HOME}/host/core/"
    cp -f "${REPO_ROOT}/host/transports/"*.py "${ARCADELED_HOME}/host/transports/"
    cp -f "${REPO_ROOT}/host/adapters/batocera/game_selected.sh" "${ARCADELED_HOME}/host/adapters/batocera/"

    for cfg in settings.json games.json; do
        if [ -f "${ARCADELED_HOME}/host/config/${cfg}" ]; then
            echo "Preserving existing user config: ${ARCADELED_HOME}/host/config/${cfg}"
        else
            cp "${REPO_ROOT}/host/config/${cfg}" "${ARCADELED_HOME}/host/config/${cfg}"
        fi
    done
fi

# Install EmulationStation game-selected hook script
if [ -f "${ES_HOOK_FILE}" ] && [ "$DRY_RUN" -eq 0 ]; then
    BACKUP="${ES_HOOK_FILE}.bak.$(date '+%Y%m%d%H%M%S')"
    cp "${ES_HOOK_FILE}" "${BACKUP}"
    echo "Backed up existing hook to ${BACKUP}"
fi

run_cmd cp "${REPO_ROOT}/host/adapters/batocera/game_selected.sh" "${ES_HOOK_FILE}"
run_cmd chmod +x "${ES_HOOK_FILE}"
run_cmd chmod +x "${ARCADELED_HOME}/host/main.py"

echo ""
echo "=== Installation Complete ==="
echo "Next steps to verify Phase 1 on Batocera:"
echo "  1. Start the local daemon in an SSH session (recommended for fast scrolling):"
echo "       python3 ${ARCADELED_HOME}/host/main.py daemon"
echo "  2. Browse games in EmulationStation and watch real-time events in:"
echo "       tail -f ${ARCADELED_HOME}/host/logs/events.log"
echo "  3. (Optional) To auto-start the daemon on boot, append this line manually to"
echo "     /userdata/system/custom.sh (this installer does NOT auto-modify custom.sh):"
echo "       python3 ${ARCADELED_HOME}/host/main.py daemon >/userdata/system/arcadeled/host/logs/daemon.log 2>&1 &"
