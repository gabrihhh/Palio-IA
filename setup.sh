#!/usr/bin/env bash
# =============================================================================
# setup.sh — Setup Script
# =============================================================================
# Execute este script UMA VEZ, com internet, no Rock Pi 4B.
#
# O que ele faz:
#   1. Verifica conexão com internet
#   2. Atualiza o sistema
#   3. Instala dependências do sistema (apt)
#   4. Cria venv Python com as dependências do projeto
#   5. Baixa o modelo de voz Vosk PT-BR
#   6. Instala o Ollama e baixa o modelo llama3.2:3b
#   7. Instala e habilita o serviço systemd (boot automático)
#   8. Configura PipeWire/WirePlumber para A2DP sink+source simultâneo
#
# Uso:
#   git clone <repo> Palio-IA
#   cd Palio-IA
#   bash setup.sh
# =============================================================================

set -euo pipefail

# --- Cores ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log()     { echo -e "${GREEN}[PALIO]${NC} $*"; }
warn()    { echo -e "${YELLOW}[AVISO]${NC} $*"; }
error()   { echo -e "${RED}[ERRO]${NC} $*"; exit 1; }
section() { echo -e "\n${BLUE}=== $* ===${NC}"; }

# --- Diretório do projeto ---
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USER_NAME="root"
USER_HOME="/root"

# Para root: define runtime dir do PipeWire
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/0}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"

log "Diretório do projeto: $PROJECT_DIR"
log "Usuário: $USER_NAME"

# =============================================================================
# 1. Verificações iniciais
# =============================================================================
section "Verificando pré-requisitos"

# Requer root
if [[ $EUID -ne 0 ]]; then
    error "Execute como root: sudo bash setup.sh"
fi

# Verifica internet
log "Verificando conexão com internet..."
if ! curl -s --max-time 5 https://google.com > /dev/null 2>&1; then
    error "Sem conexão com internet. Conecte o Rock Pi 4B à rede e tente novamente."
fi
log "Internet OK."

# =============================================================================
# 2. Atualizar sistema
# =============================================================================
section "Atualizando sistema"
apt update -y
apt upgrade -y
log "Sistema atualizado."

# =============================================================================
# 3. Dependências do sistema (apt)
# =============================================================================
section "Instalando dependências do sistema"

apt install -y \
    git \
    curl \
    wget \
    unzip \
    python3 \
    python3-pip \
    python3-dev \
    python3-venv \
    python3-dbus \
    portaudio19-dev \
    libportaudio2 \
    libportaudiocpp0 \
    espeak-ng \
    espeak-ng-data \
    libespeak-ng-dev \
    bluez \
    bluez-tools \
    pipewire \
    pipewire-pulse \
    pipewire-audio-client-libraries \
    wireplumber \
    libspa-0.2-bluetooth \
    alsa-utils \
    libasound2-dev

# Garante que espeak é encontrado pelo pyttsx3
if ! command -v espeak &> /dev/null; then
    ln -sf /usr/bin/espeak-ng /usr/local/bin/espeak
    log "Symlink espeak → espeak-ng criado."
fi

log "Dependências do sistema instaladas."

# =============================================================================
# 4. Venv Python
# =============================================================================
section "Configurando ambiente Python"

VENV_DIR="$PROJECT_DIR/venv"

# --system-site-packages permite acesso ao python3-dbus instalado pelo apt
python3 -m venv --system-site-packages "$VENV_DIR"

# Instala dependências Python
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$PROJECT_DIR/req.txt"

log "Venv criado em $VENV_DIR."

# =============================================================================
# 5. Modelo de voz Vosk PT-BR
# =============================================================================
section "Baixando modelo de voz Vosk PT-BR"

VOSK_DIR="$PROJECT_DIR/model-ptbr"
VOSK_URL="https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip"
VOSK_ZIP="/tmp/vosk-model-pt.zip"

if [[ -d "$VOSK_DIR" ]]; then
    warn "Modelo Vosk já existe em $VOSK_DIR — pulando download."
else
    log "Baixando modelo (~31 MB)..."
    wget -q --show-progress -O "$VOSK_ZIP" "$VOSK_URL"

    log "Extraindo modelo..."
    unzip -q "$VOSK_ZIP" -d /tmp/vosk-extract
    mv /tmp/vosk-extract/vosk-model-small-pt-0.3 "$VOSK_DIR"
    rm -f "$VOSK_ZIP"
    rm -rf /tmp/vosk-extract

    log "Modelo Vosk instalado em $VOSK_DIR."
fi

# =============================================================================
# 6. Ollama + modelo LLM
# =============================================================================
section "Instalando Ollama"

if command -v ollama &> /dev/null; then
    warn "Ollama já instalado ($(ollama --version)) — pulando instalação."
else
    log "Baixando e instalando Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
    log "Ollama instalado."
fi

# Inicia Ollama em background para baixar o modelo
log "Iniciando Ollama temporariamente para baixar o modelo..."
ollama serve &
OLLAMA_PID=$!
sleep 5  # aguarda o servidor subir

log "Baixando modelo llama3.2:3b (~2 GB — pode demorar alguns minutos)..."
if ollama list | grep -q "llama3.2:3b"; then
    warn "Modelo llama3.2:3b já existe — pulando download."
else
    ollama pull llama3.2:3b
    log "Modelo llama3.2:3b baixado."
fi

# Para o Ollama temporário
kill $OLLAMA_PID 2>/dev/null || true
wait $OLLAMA_PID 2>/dev/null || true
log "Ollama configurado."

# =============================================================================
# 7. Configurar Bluetooth
# =============================================================================
section "Configurando Bluetooth"

BT_CONF="/etc/bluetooth/main.conf"

if grep -q "AutoEnable=true" "$BT_CONF" 2>/dev/null; then
    warn "Bluetooth já configurado — pulando."
else
    # Habilita auto-power no boot
    if grep -q "\[Policy\]" "$BT_CONF" 2>/dev/null; then
        sed -i '/\[Policy\]/a AutoEnable=true' "$BT_CONF"
    else
        echo -e "\n[Policy]\nAutoEnable=true" >> "$BT_CONF"
    fi
    log "Bluetooth configurado para ligar automaticamente no boot."
fi

systemctl enable bluetooth
systemctl restart bluetooth

# =============================================================================
# 8. Serviço systemd (boot automático)
# =============================================================================
section "Configurando serviços systemd"

# --- Ollama ---
OLLAMA_SERVICE="/etc/systemd/system/ollama.service"
if [[ ! -f "$OLLAMA_SERVICE" ]]; then
    cat > "$OLLAMA_SERVICE" << 'EOF'
[Unit]
Description=Ollama LLM Server
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/ollama serve
Restart=on-failure
RestartSec=5
Environment="OLLAMA_HOST=127.0.0.1:11434"

[Install]
WantedBy=multi-user.target
EOF
    log "Serviço ollama.service criado."
fi

# --- Palio-IA ---
SERVICE_FILE="/etc/systemd/system/palio-ia.service"

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Palio-IA Voice Assistant
After=network.target bluetooth.target sound.target ollama.service
Wants=bluetooth.target

[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_DIR
ExecStartPre=/bin/sleep 8
ExecStart=$PROJECT_DIR/venv/bin/python main.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
Environment="PYTHONUNBUFFERED=1"
Environment="XDG_RUNTIME_DIR=/run/user/0"
Environment="DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/0/bus"

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ollama.service
systemctl enable palio-ia.service

log "Serviços systemd configurados."

# =============================================================================
# 9. Configuração de áudio (PipeWire + Bluetooth A2DP sink + P2)
# =============================================================================
section "Configurando áudio (PipeWire + P2)"

BT_CONFIG_SCRIPT="$PROJECT_DIR/scripts/bluetooth_config.sh"

if [[ -f "$BT_CONFIG_SCRIPT" ]]; then
    chmod +x "$BT_CONFIG_SCRIPT"
    log "Executando scripts/bluetooth_config.sh..."
    bash "$BT_CONFIG_SCRIPT"
    log "Configuração de áudio Bluetooth concluída."
else
    warn "scripts/bluetooth_config.sh não encontrado — pulando configuração de áudio BT."
    warn "Execute manualmente após o clone: bash scripts/bluetooth_config.sh"
fi

# =============================================================================
# Resumo final
# =============================================================================
section "Setup concluído!"

echo ""
echo -e "${GREEN}Tudo instalado com sucesso. Resumo:${NC}"
echo ""
echo -e "  Projeto:         $PROJECT_DIR"
echo -e "  Venv:            $VENV_DIR"
echo -e "  Modelo Vosk:     $VOSK_DIR"
echo -e "  Modelo LLM:      llama3.2:3b (via Ollama)"
echo -e "  Boot automático: palio-ia.service + ollama.service (systemd)"
echo -e "  Áudio:           PipeWire A2DP sink → saída P2"
echo ""
echo -e "${YELLOW}Próximos passos:${NC}"
echo ""
echo -e "  1. Conecte o cabo P2 do Rock Pi na entrada AUX do rádio"
echo -e "  2. Reinicie para testar o boot automático:"
echo -e "     ${BLUE}reboot${NC}"
echo ""
echo -e "  3. Após o boot, diga ${GREEN}'carro modo de pareamento'${NC} para parear o celular"
echo -e "     (vá nas configurações de BT do celular e conecte ao Rock Pi)"
echo ""
echo -e "  4. Diga ${GREEN}'carro toca'${NC} para testar o controle de música"
echo ""
echo -e "${GREEN}Para ver os logs em tempo real:${NC}"
echo -e "  ${BLUE}journalctl -u palio-ia.service -f${NC}"
echo ""
