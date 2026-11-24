#!/bin/bash
# Deploy ArcadeLED to Batocera over SSH.
#
# Reads default connection info from ssh_info.txt (if present) or accepts
# flags/env vars:
#   SSH_HOST / --host <ip>
#   SSH_USER / --user <user>
#   SSH_PORT / --port <port>
#   --update-configs   Overwrite remote settings.json, games.json, mame_controls_cache.json
#   --no-restart       Skip restarting the ArcadeLED daemon after deploy
#   --dry-run          Print commands without executing them

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SSH_INFO_FILE="${REPO_ROOT}/ssh_info.txt"

SSH_USER="${SSH_USER:-root}"
SSH_HOST="${SSH_HOST:-}"
SSH_PORT="${SSH_PORT:-22}"
SSH_PASS="${SSH_PASS:-}"
ARCADELED_HOME="${ARCADELED_HOME:-/userdata/system/arcadeled}"
ES_HOOK_FILE="/userdata/system/configs/emulationstation/scripts/game-selected/arcadeled_game_selected.sh"

UPDATE_CONFIGS=0
RESTART_DAEMON=1
DRY_RUN=0

# Parse ssh_info.txt if present and host/user not explicitly overridden
if [ -f "${SSH_INFO_FILE}" ]; then
    while IFS=':' read -r key val; do
        key="$(echo "${key}" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')"
        val="$(echo "${val}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
        case "${key}" in
            username|user) [ -z "${SSH_USER}" ] && SSH_USER="${val}" || true ;;
            ip|host)       [ -z "${SSH_HOST}" ] && SSH_HOST="${val}" || true ;;
            password|pass) [ -z "${SSH_PASS}" ] && SSH_PASS="${val}" || true ;;
            port)          [ "${SSH_PORT}" = "22" ] && [ -n "${val}" ] && SSH_PORT="${val}" || true ;;
        esac
    done < "${SSH_INFO_FILE}"
fi

while [ "$#" -gt 0 ]; do
    case "$1" in
        --host)           SSH_HOST="${2:?Missing value for --host}"; shift 2 ;;
        --user)           SSH_USER="${2:?Missing value for --user}"; shift 2 ;;
        --port)           SSH_PORT="${2:?Missing value for --port}"; shift 2 ;;
        --update-configs) UPDATE_CONFIGS=1; shift ;;
        --no-restart)     RESTART_DAEMON=0; shift ;;
        --dry-run)        DRY_RUN=1; shift ;;
        -h|--help)
            sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

if [ -z "${SSH_HOST}" ]; then
    echo "Error: SSH host not specified. Pass --host <ip> or set it in ssh_info.txt." >&2
    exit 1
fi

TARGET="${SSH_USER}@${SSH_HOST}"
SSH_OPTS=(-p "${SSH_PORT}" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10)
SCP_OPTS=(-P "${SSH_PORT}" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10)

USE_SSHPASS=0
if [ -n "${SSH_PASS}" ] && command -v sshpass >/dev/null 2>&1; then
    USE_SSHPASS=1
fi

run_ssh() {
    if [ "${DRY_RUN}" -eq 1 ]; then
        echo "[DRY-RUN] ssh ${TARGET} $*"
        return 0
    fi
    if [ "${USE_SSHPASS}" -eq 1 ]; then
        SSHPASS="${SSH_PASS}" sshpass -e ssh "${SSH_OPTS[@]}" "${TARGET}" "$@"
    else
        ssh "${SSH_OPTS[@]}" "${TARGET}" "$@"
    fi
}

run_scp() {
    if [ "${DRY_RUN}" -eq 1 ]; then
        echo "[DRY-RUN] scp $*"
        return 0
    fi
    if [ "${USE_SSHPASS}" -eq 1 ]; then
        SSHPASS="${SSH_PASS}" sshpass -e scp "${SCP_OPTS[@]}" "$@"
    else
        scp "${SCP_OPTS[@]}" "$@"
    fi
}

echo "=== ArcadeLED SSH Deploy ==="
echo "Target         : ${TARGET}:${SSH_PORT}"
echo "Remote dir     : ${ARCADELED_HOME}"
echo "Update configs : $([ "${UPDATE_CONFIGS}" -eq 1 ] && echo yes || echo no)"
echo "Restart daemon : $([ "${RESTART_DAEMON}" -eq 1 ] && echo yes || echo no)"
echo ""

# 1. Prepare remote directories
run_ssh "mkdir -p '${ARCADELED_HOME}/host/core' '${ARCADELED_HOME}/host/transports' '${ARCADELED_HOME}/host/adapters/batocera' '${ARCADELED_HOME}/host/config' '${ARCADELED_HOME}/host/logs' '$(dirname "${ES_HOOK_FILE}")'"

# 2. Upload host application files
run_scp "${REPO_ROOT}/host/__init__.py" "${REPO_ROOT}/host/main.py" "${TARGET}:${ARCADELED_HOME}/host/"
run_scp "${REPO_ROOT}/host/core/"*.py "${TARGET}:${ARCADELED_HOME}/host/core/"
run_scp "${REPO_ROOT}/host/transports/"*.py "${TARGET}:${ARCADELED_HOME}/host/transports/"
run_scp "${REPO_ROOT}/host/adapters/batocera/game_selected.sh" "${TARGET}:${ARCADELED_HOME}/host/adapters/batocera/"

# 3. Upload config files (preserve existing unless --update-configs is passed)
for cfg in settings.json games.json mame_controls_cache.json; do
    if [ "${UPDATE_CONFIGS}" -eq 1 ]; then
        run_scp "${REPO_ROOT}/host/config/${cfg}" "${TARGET}:${ARCADELED_HOME}/host/config/${cfg}"
    else
        if [ "${DRY_RUN}" -eq 1 ]; then
            echo "[DRY-RUN] Upload ${cfg} only if missing on remote"
        elif ! run_ssh "test -f '${ARCADELED_HOME}/host/config/${cfg}'"; then
            run_scp "${REPO_ROOT}/host/config/${cfg}" "${TARGET}:${ARCADELED_HOME}/host/config/${cfg}"
        else
            echo "Preserving remote config: ${ARCADELED_HOME}/host/config/${cfg}"
        fi
    fi
done

# 4. Install EmulationStation game-selected hook
run_ssh "if [ -f '${ES_HOOK_FILE}' ]; then cp '${ES_HOOK_FILE}' '${ES_HOOK_FILE}.bak.'\$(date '+%Y%m%d%H%M%S'); fi"
run_scp "${REPO_ROOT}/host/adapters/batocera/game_selected.sh" "${TARGET}:${ES_HOOK_FILE}"
run_ssh "chmod +x '${ES_HOOK_FILE}' '${ARCADELED_HOME}/host/main.py' '${ARCADELED_HOME}/host/adapters/batocera/game_selected.sh'"

# 5. Restart daemon if requested
if [ "${RESTART_DAEMON}" -eq 1 ]; then
    echo "Restarting ArcadeLED daemon on ${SSH_HOST}..."
    run_ssh "pkill -f '${ARCADELED_HOME}/host/main.py daemon' >/dev/null 2>&1 || true; sleep 0.3; nohup python3 '${ARCADELED_HOME}/host/main.py' daemon >'${ARCADELED_HOME}/host/logs/daemon.log' 2>&1 &"
fi

echo ""
echo "=== Deploy Complete ==="
echo "Check daemon log : ssh ${TARGET} 'tail -f ${ARCADELED_HOME}/host/logs/daemon.log'"
echo "Check event log  : ssh ${TARGET} 'tail -f ${ARCADELED_HOME}/host/logs/events.log'"

