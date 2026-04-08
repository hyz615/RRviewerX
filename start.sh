#!/usr/bin/env bash

set -euo pipefail

MODE="local"
BACKEND_PORT=8000
FRONTEND_PORT=80
WORKERS=0
NO_BROWSER=0
SKIP_DEPS=0

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

write_step() { printf '  > %s\n' "$1"; }
write_ok() { printf '  + %s\n' "$1"; }
write_warn() { printf '  ! %s\n' "$1"; }
write_err() { printf '  x %s\n' "$1" >&2; }

write_banner() {
  printf '\n'
  printf '  ========================================\n'
  printf '         RRviewerX Dev Launcher           \n'
  printf '  ========================================\n'
  printf '\n'
}

usage() {
  cat <<'EOF'
Usage:
  ./start.sh [--mode local|docker] [--backend-port 8000] [--frontend-port 8080]
             [--workers 0] [--no-browser] [--skip-deps]

Examples:
  ./start.sh
  ./start.sh --mode docker
  ./start.sh --backend-port 8001 --frontend-port 8080 --workers 2 --skip-deps
  ./start.sh -Mode local -BackendPort 8001 -FrontendPort 8080 -Workers 2 -SkipDeps
EOF
}

test_cmd() {
  command -v "$1" >/dev/null 2>&1
}

is_integer() {
  [[ "$1" =~ ^[0-9]+$ ]]
}

assert_port_value() {
  local port="$1"
  local label="$2"

  if ! is_integer "$port" || (( port < 1 || port > 65535 )); then
    write_err "$label must be an integer between 1 and 65535."
    exit 1
  fi
}

assert_workers_value() {
  local workers="$1"

  if ! is_integer "$workers" || (( workers < 0 || workers > 32 )); then
    write_err "Workers must be an integer between 0 and 32."
    exit 1
  fi
}

test_port_busy() {
  local port="$1"
  ss -ltnH "( sport = :$port )" 2>/dev/null | grep -q .
}

assert_port_free() {
  local port="$1"
  local label="$2"

  if test_port_busy "$port"; then
    write_err "Port $port ($label) is already in use."
    write_err "Run: ss -ltnp '( sport = :$port )'"
    exit 1
  fi
}

find_python() {
  local cmd
  local version

  for cmd in python3 python; do
    if test_cmd "$cmd"; then
      version="$("$cmd" --version 2>&1 || true)"
      if [[ "$version" == Python\ 3* ]]; then
        printf '%s\n' "$cmd"
        return 0
      fi
    fi
  done

  write_err "Python 3 not found. Install python3 and python3-venv first."
  exit 1
}

VENV_PYTHON=""

ensure_venv() {
  if [[ -x ".venv/bin/python" ]]; then
    VENV_PYTHON=".venv/bin/python"
    write_ok "Virtual environment found"
    return
  fi

  if [[ -x ".venv/bin/python3" ]]; then
    VENV_PYTHON=".venv/bin/python3"
    write_ok "Virtual environment found"
    return
  fi

  write_step "Creating virtual environment (.venv) ..."
  local py_cmd
  py_cmd="$(find_python)"

  if ! "$py_cmd" -m venv .venv; then
    write_err "Failed to create .venv. On Ubuntu run: sudo apt install -y python3-venv"
    exit 1
  fi

  if [[ -x ".venv/bin/python" ]]; then
    VENV_PYTHON=".venv/bin/python"
  elif [[ -x ".venv/bin/python3" ]]; then
    VENV_PYTHON=".venv/bin/python3"
  else
    write_err "Failed to locate the virtual environment interpreter."
    exit 1
  fi

  write_ok "Virtual environment created"
}

install_deps() {
  local req="backend/requirements.txt"

  if [[ ! -f "$req" ]]; then
    write_warn "$req not found, skipping dependency install"
    return
  fi

  # Ensure tesseract-ocr is installed (needed by pytesseract)
  if ! test_cmd tesseract; then
    write_step "Installing tesseract-ocr ..."
    if test_cmd apt-get; then
      sudo apt-get update -qq && sudo apt-get install -y --no-install-recommends tesseract-ocr
    elif test_cmd dnf; then
      sudo dnf install -y tesseract
    elif test_cmd yum; then
      sudo yum install -y tesseract
    else
      write_warn "Cannot auto-install tesseract-ocr. Please install it manually."
    fi
    if test_cmd tesseract; then
      write_ok "tesseract-ocr installed"
    fi
  else
    write_ok "tesseract-ocr found"
  fi

  # Ensure pip is available inside the venv (some distros strip it)
  if ! "$VENV_PYTHON" -m pip --version >/dev/null 2>&1; then
    write_step "Bootstrapping pip in venv ..."
    "$VENV_PYTHON" -m ensurepip --default-pip 2>/dev/null \
      || { write_err "pip missing and ensurepip failed. Run: sudo apt install -y python3-pip python3-venv && rm -rf .venv"; exit 1; }
    write_ok "pip bootstrapped"
  fi

  write_step "Installing backend dependencies ..."
  "$VENV_PYTHON" -m pip install --quiet --upgrade pip
  "$VENV_PYTHON" -m pip install --quiet -r "$req"
  write_ok "Dependencies installed"
}

build_allowed_origins() {
  local fe_port="$1"
  local ip
  local joined=""
  # For default HTTP port (80), browsers omit the port from the Origin header.
  local port_suffix=":$fe_port"
  if (( fe_port == 80 )); then
    port_suffix=""
  fi
  local origins=(
    "http://localhost${port_suffix}"
    "http://127.0.0.1${port_suffix}"
    "http://localhost:5173"
    "http://localhost:3000"
  )

  for ip in $(hostname -I 2>/dev/null || true); do
    if [[ "$ip" == *:* ]] || [[ "$ip" == 127.* ]]; then
      continue
    fi
    origins+=("http://${ip}${port_suffix}")
  done

  for ip in "${origins[@]}"; do
    if [[ -n "$joined" ]]; then
      joined+=","
    fi
    joined+="$ip"
  done

  printf '%s\n' "$joined"
}

start_backend() {
  local port="$1"
  local fe_port="$2"
  local workers="$3"
  local allowed_origins
  local -a args
  local backend_pid

  assert_port_free "$port" "backend"
  mkdir -p .run
  allowed_origins="$(build_allowed_origins "$fe_port")"
  args=( -m uvicorn app.main:app --host 0.0.0.0 --port "$port" --app-dir backend )

  if (( workers > 0 )); then
    args+=( --workers "$workers" )
  fi

  write_step "Starting backend -> http://localhost:$port"
  ALLOWED_ORIGINS="$allowed_origins" nohup "$VENV_PYTHON" "${args[@]}" > .run/backend.log 2>&1 &
  backend_pid=$!
  echo "$backend_pid" > .run/backend.pid
  sleep 1

  if ! kill -0 "$backend_pid" 2>/dev/null; then
    write_err "Backend failed to start. Check .run/backend.log"
    exit 1
  fi

  write_ok "Backend started (PID $backend_pid)"
}

start_frontend() {
  local port="$1"
  local be_port="$2"
  local pages_dir="frontend/src/pages"
  local frontend_pid

  # When nginx is available we will reconfigure & reload it, so skip the port check.
  if ! test_cmd nginx; then
    assert_port_free "$port" "frontend"
  fi

  if [[ ! -d "$pages_dir" ]]; then
    write_err "Frontend directory missing: $pages_dir"
    exit 1
  fi

  if [[ -f "logo.png" ]]; then
    mkdir -p "$pages_dir/assets"
    if [[ ! -f "$pages_dir/assets/logo.png" ]] || [[ "logo.png" -nt "$pages_dir/assets/logo.png" ]]; then
      cp -f "logo.png" "$pages_dir/assets/logo.png"
    fi
  fi

  # Prefer nginx (reverse-proxies backend on same port — no need to expose :8000)
  if test_cmd nginx; then
    local abs_pages
    abs_pages="$(cd "$pages_dir" && pwd)"
    local conf_dir="/etc/nginx/sites-enabled"
    local conf_avail="/etc/nginx/sites-available"
    local conf_file="rrviewer.conf"

    write_step "Configuring nginx reverse-proxy (port $port -> backend $be_port) ..."
    sed \
      -e "s|__FRONTEND_PORT__|$port|g" \
      -e "s|__BACKEND_PORT__|$be_port|g" \
      -e "s|__PAGES_DIR__|$abs_pages|g" \
      nginx-site.conf.template > ".run/$conf_file"

    # Install config into nginx
    if [[ -d "$conf_avail" ]]; then
      sudo cp -f ".run/$conf_file" "$conf_avail/$conf_file"
      sudo ln -sf "$conf_avail/$conf_file" "$conf_dir/$conf_file"
      # Remove default site if it conflicts on same port
      if [[ -e "$conf_dir/default" ]]; then
        sudo rm -f "$conf_dir/default"
      fi
    else
      # Fallback: put config in conf.d
      sudo cp -f ".run/$conf_file" "/etc/nginx/conf.d/$conf_file"
    fi

    sudo nginx -t 2>/dev/null || { write_err "nginx config test failed"; exit 1; }
    sudo systemctl reload nginx 2>/dev/null \
      || sudo nginx -s reload 2>/dev/null \
      || { write_err "Failed to reload nginx"; exit 1; }

    write_ok "Frontend started via nginx (port $port, reverse-proxy to backend $be_port)"
    echo "nginx" > .run/frontend.pid
    return
  fi

  # Fallback: Python http.server (no reverse-proxy — port 8000 must be reachable)
  write_warn "nginx not found; using Python http.server (port $be_port must be open externally)"
  write_step "Starting frontend -> http://localhost:$port"
  nohup "$VENV_PYTHON" -m http.server "$port" --directory "$pages_dir" > .run/frontend.log 2>&1 &
  frontend_pid=$!
  echo "$frontend_pid" > .run/frontend.pid
  sleep 1

  if ! kill -0 "$frontend_pid" 2>/dev/null; then
    write_err "Frontend failed to start. Check .run/frontend.log"
    exit 1
  fi

  write_ok "Frontend started (PID $frontend_pid)"
}

start_docker() {
  if ! test_cmd docker; then
    write_err "Docker is not installed or not on PATH."
    exit 1
  fi

  if ! docker compose version >/dev/null 2>&1; then
    write_err "Docker Compose plugin is not available."
    exit 1
  fi

  if (( BACKEND_PORT != 8000 || FRONTEND_PORT != 80 )); then
    write_warn "Custom ports are ignored in docker mode. docker-compose.yml exposes 8000/80."
  fi

  write_step "Building and starting containers (docker compose) ..."
  docker compose up --build -d
  write_ok "Docker services started"
}

open_browser() {
  local url="$1"

  if (( NO_BROWSER == 1 )); then
    return
  fi

  if test_cmd xdg-open; then
    xdg-open "$url" >/dev/null 2>&1 || true
  else
    write_warn "xdg-open not found. Open $url manually."
  fi
}

while (( $# > 0 )); do
  case "$1" in
    -m|--mode|-Mode)
      MODE="${2:-}"
      shift 2
      ;;
    -b|--backend-port|-BackendPort)
      BACKEND_PORT="${2:-}"
      shift 2
      ;;
    -f|--frontend-port|-FrontendPort)
      FRONTEND_PORT="${2:-}"
      shift 2
      ;;
    -w|--workers|-Workers)
      WORKERS="${2:-}"
      shift 2
      ;;
    --no-browser|-NoBrowser)
      NO_BROWSER=1
      shift
      ;;
    --skip-deps|-SkipDeps)
      SKIP_DEPS=1
      shift
      ;;
    -h|--help|-Help)
      usage
      exit 0
      ;;
    *)
      write_err "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

case "$MODE" in
  local|docker)
    ;;
  *)
    write_err "Mode must be local or docker."
    exit 1
    ;;
esac

assert_port_value "$BACKEND_PORT" "BackendPort"
assert_port_value "$FRONTEND_PORT" "FrontendPort"
assert_workers_value "$WORKERS"

write_banner

# Kill previous run's backend if still alive
stop_previous() {
  if [[ -f .run/backend.pid ]]; then
    local old_pid
    old_pid="$(cat .run/backend.pid 2>/dev/null || true)"
    if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
      write_step "Stopping previous backend (PID $old_pid) ..."
      kill "$old_pid" 2>/dev/null || true
      sleep 1
      # Force-kill if still alive
      kill -0 "$old_pid" 2>/dev/null && kill -9 "$old_pid" 2>/dev/null || true
      write_ok "Previous backend stopped"
    fi
    rm -f .run/backend.pid
  fi
  if [[ -f .run/frontend.pid ]]; then
    local fe_pid
    fe_pid="$(cat .run/frontend.pid 2>/dev/null || true)"
    if [[ "$fe_pid" == "nginx" ]]; then
      : # nginx will be reloaded, no need to stop
    elif [[ -n "$fe_pid" ]] && kill -0 "$fe_pid" 2>/dev/null; then
      write_step "Stopping previous frontend (PID $fe_pid) ..."
      kill "$fe_pid" 2>/dev/null || true
      write_ok "Previous frontend stopped"
    fi
    rm -f .run/frontend.pid
  fi
}

case "$MODE" in
  local)
    stop_previous
    ensure_venv

    if (( SKIP_DEPS == 0 )); then
      install_deps
    else
      write_warn "Skipping dependency install (--skip-deps)"
    fi

    start_backend "$BACKEND_PORT" "$FRONTEND_PORT" "$WORKERS"
    start_frontend "$FRONTEND_PORT" "$BACKEND_PORT"

    printf '\n'
    printf '  -----------------------------------------\n'
    printf '    Frontend : http://localhost:%s/index.html\n' "$FRONTEND_PORT"
    printf '    Backend  : http://localhost:%s\n' "$BACKEND_PORT"
    printf '    Logs     : .run/backend.log, .run/frontend.log\n'
    if [[ -f .run/frontend.pid ]] && grep -q nginx .run/frontend.pid 2>/dev/null; then
      printf '    Stop     : kill $(cat .run/backend.pid); sudo nginx -s stop\n'
    else
      printf '    Stop     : kill $(cat .run/backend.pid) $(cat .run/frontend.pid)\n'
    fi
    printf '  -----------------------------------------\n'
    printf '\n'

    open_browser "http://localhost:$FRONTEND_PORT/index.html"
    ;;
  docker)
    start_docker
    printf '\n'
    write_ok "Frontend -> http://localhost   Backend -> http://localhost:8000"
    printf '\n'
    ;;
esac