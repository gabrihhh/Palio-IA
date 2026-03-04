#!/usr/bin/env bash
# =============================================================================
# Palio-IA — Configuração de Áudio Bluetooth (PipeWire)
# =============================================================================
# Configura o PipeWire para:
#   - Receber áudio do celular via A2DP (sink)
#   - Enviar áudio para o rádio do carro via A2DP (source)
#   - Misturar o áudio do celular com o TTS do Palio
#
# Topologia de áudio:
#
#   [Celular] --A2DP source--> [PipeWire sink    ]
#                              [PipeWire loopback ] --> [A2DP source] --> [Rádio]
#   [Palio TTS]  ------------> [PipeWire mixer   ]
#
# Este script é chamado automaticamente pelo setup.sh.
# Pode ser re-executado a qualquer momento para reconfigurar.
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

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEVICES_FILE="$PROJECT_DIR/.bluetooth_devices"

# =============================================================================
# 1. Verificar dependências
# =============================================================================
section "Verificando dependências de áudio"

for cmd in pactl pw-cli wpctl; do
    if ! command -v "$cmd" &>/dev/null; then
        error "$cmd não encontrado. Execute: sudo apt install pipewire pipewire-pulse wireplumber"
    fi
done
log "PipeWire, pactl e WirePlumber presentes."

# =============================================================================
# 2. Configurar PipeWire para suportar Bluetooth A2DP sink + source
# =============================================================================
section "Configurando PipeWire para Bluetooth"

PIPEWIRE_CONF_DIR="$HOME/.config/pipewire/pipewire.conf.d"
mkdir -p "$PIPEWIRE_CONF_DIR"

# Habilita suporte a Bluetooth no PipeWire
cat > "$PIPEWIRE_CONF_DIR/10-bluetooth.conf" << 'EOF'
# Palio-IA: habilita Bluetooth A2DP sink + source simultâneo
context.properties = {
    default.clock.rate          = 48000
    default.clock.quantum       = 1024
    default.clock.min-quantum   = 32
    default.clock.max-quantum   = 8192
}

context.modules = [
    {   name = libpipewire-module-bluetooth-autoconnect
        args = {}
    }
]
EOF

log "Configuração base do PipeWire criada."

# =============================================================================
# 3. Configurar WirePlumber para gerenciar os perfis Bluetooth
# =============================================================================

WIREPLUMBER_CONF_DIR="$HOME/.config/wireplumber/wireplumber.conf.d"
mkdir -p "$WIREPLUMBER_CONF_DIR"

# Configuração para aceitar conexão A2DP do celular como sink
# e conectar ao rádio como source
cat > "$WIREPLUMBER_CONF_DIR/51-palio-bluetooth.conf" << 'EOF'
# Palio-IA: política de Bluetooth para sink (celular) + source (rádio)
monitor.bluez.properties = {
    # Habilita todos os perfis de áudio
    bluez5.enable-sbc-xq     = true
    bluez5.enable-msbc        = true
    bluez5.enable-hw-volume   = true

    # Aceita conexões A2DP de entrada (celular)
    bluez5.a2dp.aac.bitratemode = 0

    # Roles: o Rock Pi age como sink E source
    bluez5.roles = [
        a2dp_sink
        a2dp_source
        hsp_hs
        hfp_hf
    ]
}
EOF

log "Configuração do WirePlumber criada."

# =============================================================================
# 4. Criar loopback virtual: celular → rádio
# =============================================================================
section "Configurando loopback de áudio (celular → rádio)"

# Configuração do módulo de loopback no PipeWire
# Isso cria um "tubo" do sink (celular) para o source (rádio)
# O TTS do Palio usa o mesmo sink padrão do sistema, então é misturado automaticamente
cat > "$PIPEWIRE_CONF_DIR/20-loopback.conf" << 'EOF'
# Palio-IA: loopback — mistura áudio do celular + TTS e envia ao rádio
context.modules = [
    {   name = libpipewire-module-loopback
        args = {
            # Nome do nó de loopback
            node.name = "palio-loopback"
            node.description = "Palio Audio Loopback"

            # Latência (em samples @ 48kHz — 2048 = ~43ms)
            capture.props = {
                node.name = "palio-loopback-capture"
                audio.position = [ FL FR ]
                stream.dont-remix = true
                node.passive = true
            }
            playback.props = {
                node.name = "palio-loopback-playback"
                audio.position = [ FL FR ]
                node.passive = true
            }
        }
    }
]
EOF

log "Loopback configurado."

# =============================================================================
# 5. Script de reconexão automática
# =============================================================================
section "Criando script de reconexão automática"

RECONNECT_SCRIPT="$PROJECT_DIR/scripts/bt_reconnect.sh"

cat > "$RECONNECT_SCRIPT" << 'RECONNECT_EOF'
#!/usr/bin/env bash
# Reconecta automaticamente os dispositivos Bluetooth do Palio-IA.
# Chamado pelo systemd após o boot.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEVICES_FILE="$PROJECT_DIR/.bluetooth_devices"

log() { echo "[BT-RECONNECT] $*"; }

if [[ ! -f "$DEVICES_FILE" ]]; then
    log "Nenhum dispositivo configurado em $DEVICES_FILE."
    exit 0
fi

# Aguarda o Bluetooth estar pronto
sleep 5
bluetoothctl power on

while IFS= read -r line; do
    [[ -z "$line" || "$line" =~ ^# ]] && continue
    MAC=$(echo "$line" | cut -d= -f2 | awk '{print $1}')
    TIPO=$(echo "$line" | cut -d= -f1)

    log "Tentando reconectar $TIPO: $MAC"

    if bluetoothctl connect "$MAC" 2>/dev/null; then
        log "$TIPO ($MAC) reconectado."

        # Configura o perfil A2DP correto para cada dispositivo
        sleep 2
        CARD=$(pactl list cards short 2>/dev/null | grep "${MAC//:/_}" | awk '{print $1}' || true)
        if [[ -n "$CARD" ]]; then
            if [[ "$TIPO" == "phone" ]]; then
                # Celular: perfil A2DP sink (Rock Pi recebe áudio)
                pactl set-card-profile "$CARD" a2dp-sink 2>/dev/null || \
                pactl set-card-profile "$CARD" a2dp_sink 2>/dev/null || true
                log "Perfil A2DP sink aplicado ao celular."
            elif [[ "$TIPO" == "car" ]]; then
                # Rádio: perfil A2DP source (Rock Pi envia áudio)
                pactl set-card-profile "$CARD" a2dp-source 2>/dev/null || \
                pactl set-card-profile "$CARD" a2dp_source 2>/dev/null || true
                log "Perfil A2DP source aplicado ao rádio."
            fi
        fi
    else
        log "Não foi possível reconectar $TIPO ($MAC) agora — tentará novamente."
    fi
done < "$DEVICES_FILE"
RECONNECT_EOF

chmod +x "$RECONNECT_SCRIPT"
log "Script de reconexão criado: $RECONNECT_SCRIPT"

# =============================================================================
# 6. Serviço systemd para reconexão no boot
# =============================================================================
section "Configurando reconexão automática no boot"

RECONNECT_SERVICE="/etc/systemd/system/palio-bt-reconnect.service"

sudo tee "$RECONNECT_SERVICE" > /dev/null << EOF
[Unit]
Description=Palio-IA Bluetooth Reconnect
After=bluetooth.target pipewire.service
Wants=bluetooth.target

[Service]
Type=oneshot
User=$USER
ExecStart=$RECONNECT_SCRIPT
RemainAfterExit=yes
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable palio-bt-reconnect.service
log "Serviço de reconexão habilitado."

# =============================================================================
# 7. Reiniciar PipeWire para aplicar configurações
# =============================================================================
section "Aplicando configurações"

systemctl --user daemon-reload
systemctl --user restart pipewire pipewire-pulse wireplumber 2>/dev/null || \
    warn "PipeWire não está rodando como serviço de usuário — as configurações serão aplicadas no próximo login."

# =============================================================================
# Resumo
# =============================================================================
section "Configuração de áudio concluída"

echo ""
echo "  Fluxo de áudio configurado:"
echo ""
echo -e "  ${GREEN}[Celular]${NC} ──A2DP sink──> [Rock Pi] ──loopback──> [Rock Pi] ──A2DP source──> ${GREEN}[Rádio]${NC}"
echo -e "  ${GREEN}[TTS Palio]${NC} ─────────────────────────────────────────────────────────────^"
echo ""
echo "  - O celular se conecta ao Rock Pi e envia o áudio da música"
echo "  - O Rock Pi mistura esse áudio com a voz do Palio (TTS)"
echo "  - O áudio combinado é enviado ao rádio do carro via Bluetooth"
echo ""
log "Para testar: conecte o celular e o rádio e verifique com: pactl list sinks short"
echo ""
