#!/usr/bin/env bash
#
# Oistros installer — single-line setup for Linux (including Raspberry Pi)
#
# Usage:
#   git clone https://github.com/dogacol/oistros && cd oistros && bash install.sh
#
set -euo pipefail

BOLD='\033[1m'
DIM='\033[2m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[oistros]${NC} $*"; }
warn()  { echo -e "${YELLOW}[oistros]${NC} $*"; }
error() { echo -e "${RED}[oistros]${NC} $*"; }

# ── Platform check ──────────────────────────────────────────────────
if [[ "$(uname)" != "Linux" ]]; then
    error "Oistros currently supports Linux only."
    exit 1
fi

ARCH=$(uname -m)
info "Detected architecture: ${BOLD}${ARCH}${NC}"

# ── Project directory ───────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"

if [[ ! -f "$PROJECT_DIR/pyproject.toml" ]]; then
    error "pyproject.toml not found. Run this script from the oistros repo directory."
    exit 1
fi

cd "$PROJECT_DIR"
info "Project directory: ${BOLD}${PROJECT_DIR}${NC}"

# ── Python ──────────────────────────────────────────────────────────
PYTHON=""
for cmd in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done

if [[ -z "$PYTHON" ]]; then
    info "Python 3 not found. Installing..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y -qq python3 python3-pip python3-venv
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y python3 python3-pip
    elif command -v pacman &>/dev/null; then
        sudo pacman -S --noconfirm python python-pip
    else
        error "Could not install Python 3. Please install it manually."
        exit 1
    fi
    PYTHON="python3"
fi

PY_VERSION=$("$PYTHON" --version 2>&1)
info "Using ${BOLD}${PY_VERSION}${NC}"

# ── Virtual environment + pip install ───────────────────────────────
VENV_DIR="$PROJECT_DIR/.venv"
if [[ ! -d "$VENV_DIR" ]]; then
    info "Creating virtual environment..."
    "$PYTHON" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
info "Virtual environment activated"

info "Installing oistros..."
pip install --upgrade pip -q
pip install -e . -q
info "oistros installed"

# Verify the command works
if command -v oistros &>/dev/null; then
    info "Command 'oistros' is available"
else
    info "Command available via: ${BOLD}$VENV_DIR/bin/oistros${NC}"
fi

# ── Ollama ──────────────────────────────────────────────────────────
STARTED_OLLAMA=false

if command -v ollama &>/dev/null; then
    OLLAMA_VERSION=$(ollama --version 2>&1 || echo "unknown")
    info "Ollama already installed: ${BOLD}${OLLAMA_VERSION}${NC}"
else
    info "Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
    info "Ollama installed"
fi

# ── Pull the default model ──────────────────────────────────────────
MODEL="qwen3:0.6b"
info "Pulling model ${BOLD}${MODEL}${NC} (this may take a few minutes on first run)..."

if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
    info "Starting Ollama server..."
    ollama serve &>/dev/null &
    OLLAMA_PID=$!
    sleep 3
    STARTED_OLLAMA=true
fi

ollama pull "$MODEL" || warn "Could not pull model. Pull it later with: ollama pull $MODEL"

# ── Create working directories ──────────────────────────────────────
mkdir -p "$PROJECT_DIR/output" "$PROJECT_DIR/logs"

# ── Create systemd service file ─────────────────────────────────────
cat > "$PROJECT_DIR/oistros.service" << SVCEOF
[Unit]
Description=Oistros — the philosophical gadfly
After=network-online.target ollama.service
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$VENV_DIR/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$VENV_DIR/bin/oistros
Restart=on-failure
RestartSec=60

[Install]
WantedBy=multi-user.target
SVCEOF

# ── Done ────────────────────────────────────────────────────────────
echo ""
info "${BOLD}Oistros installed successfully.${NC}"
echo ""
echo -e "  ${BOLD}Quick start:${NC}"
echo -e "    ${DIM}# Activate the virtualenv first:${NC}"
echo -e "    source .venv/bin/activate"
echo ""
echo -e "    ${DIM}# Test passage fetching + news scanning (no LLM):${NC}"
echo -e "    oistros test"
echo ""
echo -e "    ${DIM}# Run one full cycle:${NC}"
echo -e "    oistros run"
echo ""
echo -e "    ${DIM}# Start the daemon (cycle every 30 min):${NC}"
echo -e "    oistros"
echo ""
echo -e "    ${DIM}# Other commands:${NC}"
echo -e "    oistros read     ${DIM}# fetch a random passage${NC}"
echo -e "    oistros scan     ${DIM}# scan current news${NC}"
echo -e "    oistros log      ${DIM}# show recent outputs${NC}"
echo ""
echo -e "    ${DIM}# Or install as a systemd service:${NC}"
echo -e "    sudo cp oistros.service /etc/systemd/system/"
echo -e "    sudo systemctl enable --now oistros"
echo ""
echo -e "  ${BOLD}Config:${NC} $PROJECT_DIR/config.yaml"
echo -e "  ${BOLD}Output:${NC} $PROJECT_DIR/output/"
echo -e "  ${BOLD}Logs:${NC}   $PROJECT_DIR/logs/"
echo ""

if [[ "$STARTED_OLLAMA" == "true" ]]; then
    kill "$OLLAMA_PID" 2>/dev/null || true
fi
