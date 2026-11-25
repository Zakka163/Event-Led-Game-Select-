#!/bin/bash
# EmulationStation game-selected hook: $1=system, $2=rom_path, $3=game_name

ARCADELED_HOME="${ARCADELED_HOME:-/userdata/system/arcadeled}"
ARCADELED_MAIN="${ARCADELED_HOME}/host/main.py"
ARCADELED_HOST="${ARCADELED_HOST:-127.0.0.1}"
ARCADELED_PORT="${ARCADELED_PORT:-19876}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

SYSTEM_NAME="${1:-}"
ROM_PATH="${2:-}"
GAME_NAME="${3:-}"

# Guard: do nothing if host engine is missing (never break EmulationStation).
if [ ! -f "${ARCADELED_MAIN}" ]; then
    exit 0
fi

_json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\n'/ }"
    s="${s//$'\r'/ }"
    printf '%s' "$s"
}

# Dispatch in background so fast gamelist scrolling does not block ES main thread.
# Fast path: send JSON directly to daemon TCP socket (no Python startup overhead).
# Fallback: invoke python3 CLI if daemon is not reachable.
(
    PAYLOAD=$(printf '{"event":"game_selected","platform":"batocera","system":"%s","rom_path":"%s","game_name":"%s"}\n' \
        "$(_json_escape "${SYSTEM_NAME}")" \
        "$(_json_escape "${ROM_PATH}")" \
        "$(_json_escape "${GAME_NAME}")")

    if exec 3<>"/dev/tcp/${ARCADELED_HOST}/${ARCADELED_PORT}" 2>/dev/null; then
        printf '%s' "${PAYLOAD}" >&3
        exec 3>&-
        exec 3<&-
        exit 0
    fi

    "${PYTHON_BIN}" "${ARCADELED_MAIN}" emit \
        --platform "batocera" \
        --system "${SYSTEM_NAME}" \
        --rom-path "${ROM_PATH}" \
        --game-name "${GAME_NAME}" \
        --forward-to-daemon
) >/dev/null 2>&1 &

exit 0
