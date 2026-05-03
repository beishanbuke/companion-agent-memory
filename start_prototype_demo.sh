#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
RUN_DIR="$ROOT_DIR/prototype_demo/.run"
LOG_DIR="$ROOT_DIR/prototype_demo/logs"

SERVER_PID_FILE="$RUN_DIR/server.pid"
VOICE_PID_FILE="$RUN_DIR/voice_bot.pid"

SERVER_LOG_FILE="$LOG_DIR/server.log"
VOICE_LOG_FILE="$LOG_DIR/voice_bot.log"

mkdir -p "$RUN_DIR" "$LOG_DIR"

usage() {
  cat <<'EOF'
Usage:
  ./start_prototype_demo.sh             # start both services
  ./start_prototype_demo.sh start       # start both services
  ./start_prototype_demo.sh stop        # stop both services
  ./start_prototype_demo.sh restart     # restart both services
  ./start_prototype_demo.sh status      # show running status
EOF
}

require_python() {
  if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "Missing virtualenv python: $PYTHON_BIN"
    echo "Please create the quickstart .venv first."
    exit 1
  fi
}

read_pid() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]]; then
    tr -d '[:space:]' < "$pid_file"
  fi
}

is_pid_running() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

cleanup_stale_pidfile() {
  local pid_file="$1"
  local pid
  pid="$(read_pid "$pid_file")"
  if [[ -n "$pid" ]] && ! is_pid_running "$pid"; then
    rm -f "$pid_file"
  fi
}

start_service() {
  local name="$1"
  local pid_file="$2"
  local log_file="$3"
  shift 3
  local -a env_args=()

  while [[ $# -gt 0 && "$1" == *=* ]]; do
    env_args+=("$1")
    shift
  done

  cleanup_stale_pidfile "$pid_file"

  local existing_pid
  existing_pid="$(read_pid "$pid_file")"
  if is_pid_running "$existing_pid"; then
    echo "$name already running (pid=$existing_pid)"
    return 0
  fi

  (
    cd "$ROOT_DIR"
    nohup env "${env_args[@]}" "$PYTHON_BIN" "$@" >"$log_file" 2>&1 &
    echo $! > "$pid_file"
  )

  local new_pid
  new_pid="$(read_pid "$pid_file")"
  sleep 1

  if ! is_pid_running "$new_pid"; then
    echo "Failed to start $name. Last log lines:"
    tail -n 20 "$log_file" 2>/dev/null || true
    exit 1
  fi

  echo "Started $name (pid=$new_pid)"
}

stop_service() {
  local name="$1"
  local pid_file="$2"

  cleanup_stale_pidfile "$pid_file"

  local pid
  pid="$(read_pid "$pid_file")"
  if ! is_pid_running "$pid"; then
    rm -f "$pid_file"
    echo "$name is not running"
    return 0
  fi

  kill "$pid" 2>/dev/null || true

  for _ in {1..20}; do
    if ! is_pid_running "$pid"; then
      rm -f "$pid_file"
      echo "Stopped $name"
      return 0
    fi
    sleep 0.25
  done

  kill -9 "$pid" 2>/dev/null || true
  rm -f "$pid_file"
  echo "Force-stopped $name"
}

status_service() {
  local name="$1"
  local pid_file="$2"
  local pid
  pid="$(read_pid "$pid_file")"

  if is_pid_running "$pid"; then
    echo "$name: running (pid=$pid)"
  else
    echo "$name: stopped"
  fi
}

print_summary() {
  cat <<EOF

URLs:
  Memory page: http://127.0.0.1:7897
  Voice client: http://127.0.0.1:7860/client

Logs:
  $SERVER_LOG_FILE
  $VOICE_LOG_FILE
EOF
}

main() {
  local action="${1:-start}"

  case "$action" in
    start)
      require_python
      start_service \
        "prototype server" \
        "$SERVER_PID_FILE" \
        "$SERVER_LOG_FILE" \
        "PROTOTYPE_HOST=${PROTOTYPE_HOST:-0.0.0.0}" \
        prototype_demo/server.py
      start_service \
        "voice bot" \
        "$VOICE_PID_FILE" \
        "$VOICE_LOG_FILE" \
        "MEMORY_API_BASE_URL=${MEMORY_API_BASE_URL:-http://127.0.0.1:${PROTOTYPE_PORT:-7897}}" \
        prototype_demo/voice_bot.py \
        --host "${VOICE_BOT_HOST:-0.0.0.0}"
      print_summary
      ;;
    stop)
      stop_service "voice bot" "$VOICE_PID_FILE"
      stop_service "prototype server" "$SERVER_PID_FILE"
      ;;
    restart)
      "$0" stop
      "$0" start
      ;;
    status)
      status_service "prototype server" "$SERVER_PID_FILE"
      status_service "voice bot" "$VOICE_PID_FILE"
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"


  #  cd /mnt/dengzhijie/mydata/memory/pipecat/examples/quickstart
  # ./start_prototype_demo.sh

  # 默认就是一键启动 7897 和 7860。

  # 它还支持：

  # ./start_prototype_demo.sh stop
  # ./start_prototype_demo.sh status
  # ./start_prototype_demo.sh restart

  # 启动后页面地址还是：

  # - http://127.0.0.1:7897
  # - http://127.0.0.1:7860/client
