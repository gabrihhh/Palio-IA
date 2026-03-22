#!/usr/bin/env bash
# =============================================================================
# Palio-IA — Configuração de Áudio (PipeWire + Bluetooth A2DP sink + P2)
# =============================================================================
#
# O que este script faz:
#   1. Configura o WirePlumber para aceitar conexão A2DP do celular (Rock Pi = sink)
#   2. Define a saída analógica (P2/3.5mm) como default sink do sistema
#   3. O PipeWire roteia automaticamente o áudio do celular para o P2
#   4. O TTS do Palio também sai pelo P2 (usa o default sink)
#
# Arquitetura de áudio resultante:
#
#   [Celular] ──BT A2DP──► [Rock Pi / PipeWire] ──P2 cabo──► [Rádio AUX]
#                                    │
#                          TTS misturado aqui
#
# Uso:
#   bash scripts/bluetooth_config.sh
# =============================================================================

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

log()     { echo -e "${GREEN}[AUDIO]${NC} $*"; }
warn()    { echo -e "${YELLOW}[AVISO]${NC} $*"; }
error()   { echo -e "${RED}[ERRO]${NC} $*"; exit 1; }
section() { echo -e "\n${BLUE}=== $* ===${NC}"; }

# Para root, define o diretório de runtime correto do PipeWire
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"

# =============================================================================
# 1. Verificar dependências
# =============================================================================
section "Verificando dependências de áudio"

for cmd in pactl wpctl bluetoothctl; do
    if ! command -v "$cmd" &>/dev/null; then
        error "$cmd não encontrado. Execute setup.sh primeiro."
    fi
done
log "Dependências OK."

# =============================================================================
# 2. Habilitar PipeWire como serviço de usuário (para root em headless)
# =============================================================================
section "Habilitando serviços PipeWire"

# Garante que o diretório de runtime existe
mkdir -p "$XDG_RUNTIME_DIR"

# Habilita linger para que os serviços de usuário iniciem sem login interativo
loginctl enable-linger root 2>/dev/null || true

# Habilita e inicia os serviços PipeWire do usuário
systemctl --user enable pipewire pipewire-pulse wireplumber 2>/dev/null || true
systemctl --user start  pipewire pipewire-pulse wireplumber 2>/dev/null || \
    warn "PipeWire não iniciou agora — será iniciado no próximo boot."

sleep 2
log "Serviços PipeWire habilitados."

# =============================================================================
# 3. Configurar WirePlumber — Bluetooth somente A2DP sink (recebe do celular)
# =============================================================================
section "Configurando WirePlumber para Bluetooth A2DP sink"

WP_BT_DIR="$HOME/.config/wireplumber/bluetooth.lua.d"
mkdir -p "$WP_BT_DIR"

cat > "$WP_BT_DIR/50-palio-bt.lua" << 'EOF'
-- Palio-IA: Rock Pi age apenas como A2DP sink (recebe áudio do celular).
-- O rádio do carro é conectado via cabo P2 — não precisa de A2DP source.
bluez_monitor.properties = {
  -- Apenas sink: recebe áudio do celular
  ["bluez5.roles"]           = "[ a2dp_sink hsp_hs hfp_hf ]",
  ["bluez5.codecs"]          = "[ sbc sbc_xq aac ]",
  ["bluez5.enable-sbc-xq"]  = true,
  ["bluez5.enable-msbc"]     = true,
  ["bluez5.enable-hw-volume"] = true,
  -- Auto-aceita perfil A2DP sink ao conectar
  ["bluez5.auto-connect"]    = "[ a2dp_sink ]",
}
EOF

log "WirePlumber configurado para A2DP sink."

# =============================================================================
# 4. Detectar saída analógica (P2) e definir como default sink
# =============================================================================
section "Definindo saída analógica (P2) como default sink"

# Aguarda PipeWire inicializar os dispositivos
sleep 3

# Pega o primeiro sink que NÃO seja Bluetooth
ANALOG_SINK=$(pactl list sinks short 2>/dev/null \
    | grep -v -i "bluez\|bluetooth" \
    | awk 'NR==1 {print $2}' || true)

if [[ -z "$ANALOG_SINK" ]]; then
    warn "Nenhuma saída analógica detectada ainda. Defina manualmente após o boot:"
    warn "  pactl set-default-sink <nome-do-sink>"
    warn "  Para listar os sinks disponíveis: pactl list sinks short"
else
    pactl set-default-sink "$ANALOG_SINK" 2>/dev/null || true
    log "Default sink definido: $ANALOG_SINK"

    # Persiste a configuração no WirePlumber
    WP_MAIN_DIR="$HOME/.config/wireplumber/main.lua.d"
    mkdir -p "$WP_MAIN_DIR"

    cat > "$WP_MAIN_DIR/50-palio-defaults.lua" << EOF
-- Palio-IA: mantém a saída analógica (P2) como default sink.
-- Garante que o áudio do celular (BT) e o TTS saem pelo P2, não por BT.
default_policy.default_node.roles = {
    ["Audio/Sink"] = "$ANALOG_SINK",
}
EOF
    log "Default sink persistido no WirePlumber."
fi

# =============================================================================
# 5. Reiniciar WirePlumber para aplicar configurações
# =============================================================================
section "Aplicando configurações"

systemctl --user restart wireplumber 2>/dev/null || \
    warn "Não foi possível reiniciar WirePlumber agora — será aplicado no boot."

sleep 2

# =============================================================================
# 6. Verificação final
# =============================================================================
section "Verificação"

echo ""
log "Sinks disponíveis:"
pactl list sinks short 2>/dev/null || warn "PipeWire não acessível agora."

echo ""
DEFAULT_SINK=$(pactl get-default-sink 2>/dev/null || echo "desconhecido")
log "Default sink atual: $DEFAULT_SINK"

echo ""
echo -e "${GREEN}Configuração de áudio concluída.${NC}"
echo ""
echo "  Fluxo resultante:"
echo ""
echo -e "  ${GREEN}[Celular]${NC} ──BT A2DP──► [Rock Pi / PipeWire] ──cabo P2──► ${GREEN}[Rádio AUX]${NC}"
echo -e "                                       │"
echo -e "                             TTS Palio misturado aqui"
echo ""
echo "  Para verificar o roteamento após conectar o celular:"
echo -e "  ${BLUE}pw-cli list-objects | grep -A5 bluez${NC}"
echo ""
