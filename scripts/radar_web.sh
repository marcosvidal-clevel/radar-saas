#!/usr/bin/env bash
set -euo pipefail
umask 077

PROJECT_DIR="/workspaces/radar-saas"
RUNTIME_DIR="$PROJECT_DIR/.runtime"
PID_FILE="$RUNTIME_DIR/django.pid"
LOCK_DIR="$RUNTIME_DIR/django.lock"
LOG_FILE="$RUNTIME_DIR/django.log"
HOST="0.0.0.0"
PORT="8000"

mkdir -p "$RUNTIME_DIR"
chmod 700 "$RUNTIME_DIR"

is_running() {
  local pid=""
  if [ -s "$PID_FILE" ]; then
    pid="$(cat "$PID_FILE")"
    if pid_matches "$pid"; then
      return 0
    fi
  fi
  while read -r pid; do
    if pid_matches "$pid"; then
      printf '%s\n' "$pid" >"$PID_FILE"
      return 0
    fi
  done < <(pgrep -f "$PROJECT_DIR/.venv/bin/python manage.py runserver $HOST:$PORT" || true)
  return 1
}

pid_matches() {
  local pid="$1"
  kill -0 "$pid" 2>/dev/null || return 1
  ps -p "$pid" -o args= | grep -Fqx "$PROJECT_DIR/.venv/bin/python manage.py runserver $HOST:$PORT --noreload"
}

http_ready() {
  curl -sS -o /dev/null --max-time 1 "http://127.0.0.1:$PORT/" 2>/dev/null
}

status() {
  if is_running; then
    echo "Django activo (PID $(cat "$PID_FILE")); log: $LOG_FILE"
    return 0
  fi
  echo "Django detenido; log: $LOG_FILE"
  return 1
}

start() {
  if is_running; then
    echo "Django ya está activo (PID $(cat "$PID_FILE")); no se duplica el proceso."
    return 0
  fi

  if ! docker inspect -f '{{.State.Running}}' radar-postgres 2>/dev/null | grep -qx true; then
    echo "PostgreSQL radar-postgres no está activo; no se inicia Django." >&2
    return 1
  fi
  docker exec radar-postgres pg_isready -U radar -d radar >/dev/null

  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "Otro arranque de Django está en curso; no se duplica el proceso." >&2
    return 1
  fi
  trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

  if is_running; then
    echo "Django ya está activo (PID $(cat "$PID_FILE")); no se duplica el proceso."
    return 0
  fi

  cd "$PROJECT_DIR"
  nohup setsid "$PROJECT_DIR/.venv/bin/python" manage.py runserver "$HOST:$PORT" --noreload </dev/null >>"$LOG_FILE" 2>&1 &
  for _ in $(seq 1 40); do
    if is_running && http_ready; then break; fi
    sleep 0.25
  done
  if ! is_running || ! http_ready; then
    echo "Django no quedó disponible en http://127.0.0.1:$PORT/; revisar $LOG_FILE" >&2
    return 1
  fi
  chmod 600 "$PID_FILE" "$LOG_FILE"
  echo "Django iniciado (PID $(cat "$PID_FILE")); log: $LOG_FILE"
}

stop() {
  if ! [ -s "$PID_FILE" ]; then
    echo "Django ya está detenido."
    return 0
  fi
  local pid
  pid="$(cat "$PID_FILE")"
  if pid_matches "$pid"; then
    kill "$pid"
    for _ in $(seq 1 20); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.25
    done
  else
    echo "PID guardado ($pid) no corresponde al Django gestionado; no se envía ninguna señal." >&2
  fi
  rm -f "$PID_FILE"
  echo "Django detenido."
}

case "${1:-start}" in
  start) start ;;
  status) status ;;
  stop) stop ;;
  *) echo "Uso: $0 {start|status|stop}" >&2; exit 2 ;;
esac
