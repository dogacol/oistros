#!/usr/bin/env bash
#
# Oistros installer — single-line setup for Linux (including Raspberry Pi)
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/<owner>/oistros/main/install.sh | bash
#   — or —
#   git clone <repo> && cd oistros && bash install.sh
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

# ── Python ──────────────────────────────────────────────────────────
PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3; do
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

# ── Project directory ───────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"

# If we're not inside the repo (e.g. piped from curl), clone it
if [[ ! -f "$PROJECT_DIR/oistros.py" ]]; then
    if [[ -d "$HOME/oistros" ]]; then
        PROJECT_DIR="$HOME/oistros"
        info "Using existing directory at $PROJECT_DIR"
    else
        error "oistros.py not found. Please run this script from the project directory."
        exit 1
    fi
fi

cd "$PROJECT_DIR"
info "Project directory: ${BOLD}${PROJECT_DIR}${NC}"

# ── Virtual environment ─────────────────────────────────────────────
VENV_DIR="$PROJECT_DIR/.venv"
if [[ ! -d "$VENV_DIR" ]]; then
    info "Creating virtual environment..."
    "$PYTHON" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
info "Virtual environment activated"

# ── Python dependencies ─────────────────────────────────────────────
info "Installing Python dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
info "Python dependencies installed"

# ── Ollama ──────────────────────────────────────────────────────────
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

# Start ollama serve in background if not already running
if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
    info "Starting Ollama server..."
    ollama serve &>/dev/null &
    OLLAMA_PID=$!
    sleep 3
    STARTED_OLLAMA=true
else
    STARTED_OLLAMA=false
fi

ollama pull "$MODEL" || warn "Could not pull model. You can pull it later with: ollama pull $MODEL"

# ── Create directories ──────────────────────────────────────────────
mkdir -p "$PROJECT_DIR/output" "$PROJECT_DIR/logs" "$PROJECT_DIR/texts/cache"

# ── Create run script ──────────────────────────────────────────────
cat > "$PROJECT_DIR/run.sh" << 'RUNEOF'
#!/usr/bin/env bash
# Run Oistros
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/.venv/bin/activate"

# Ensure Ollama is running
if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
    echo "[oistros] Starting Ollama server..."
    ollama serve &>/dev/null &
    sleep 3
fi

exec python3 "$SCRIPT_DIR/oistros.py" "$@"
RUNEOF
chmod +x "$PROJECT_DIR/run.sh"

# ── Create systemd service (optional) ──────────────────────────────
SERVICE_FILE="$PROJECT_DIR/oistros.service"
cat > "$SERVICE_FILE" << SVCEOF
[Unit]
Description=Oistros — the philosophical gadfly
After=network-online.target ollama.service
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/run.sh daemon
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
echo -e "    ${DIM}# Test passage fetching and news scanning (no LLM needed):${NC}"
echo -e "    ./run.sh test"
echo ""
echo -e "    ${DIM}# Run one full cycle:${NC}"
echo -e "    ./run.sh once"
echo ""
echo -e "    ${DIM}# Run as a daemon (every 30 minutes):${NC}"
echo -e "    ./run.sh daemon"
echo ""
echo -e "    ${DIM}# Or use cron (every 30 min):${NC}"
echo -e "    crontab -e"
echo -e "    */30 * * * * $PROJECT_DIR/run.sh once"
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
