#!/usr/bin/env bash
# =============================================================================
# Palio-IA — Script de Pareamento Bluetooth
# =============================================================================
# Execute este script para parear o celular e o rádio do carro com o Rock Pi.
# Pode ser executado quantas vezes quiser para adicionar novos dispositivos.
#
# Uso:
#   bash scripts/pair_bluetooth.sh
#
# O script guia você pelo processo interativo de pareamento.
# Os MACs dos dispositivos são salvos em .bluetooth_devices para reconexão
# automática futura.
# =============================================================================

set -euo pipefail

# --- Cores ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log()     { echo -e "${GREEN}[BT]${NC} $*"; }
warn()    { echo -e "${YELLOW}[AVISO]${NC} $*"; }
error()   { echo -e "${RED}[ERRO]${NC} $*"; exit 1; }
info()    { echo -e "${CYAN}$*${NC}"; }
section() { echo -e "\n${BLUE}=== $* ===${NC}"; }

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEVICES_FILE="$PROJECT_DIR/.bluetooth_devices"

# =============================================================================
# Funções auxiliares
# =============================================================================

aguardar_bluetoothctl() {
    # Inicia bluetoothctl em modo batch e retorna a saída
    bluetoothctl "$@"
}

verificar_bluetooth() {
    if ! systemctl is-active --quiet bluetooth; then
        warn "Serviço Bluetooth não está rodando. Iniciando..."
        sudo systemctl start bluetooth
        sleep 2
    fi

    # Liga o adaptador
    bluetoothctl power on > /dev/null 2>&1 || true
    log "Bluetooth ativo."
}

listar_dispositivos_pareados() {
    section "Dispositivos já pareados"
    local paired
    paired=$(bluetoothctl paired-devices 2>/dev/null || true)
    if [[ -z "$paired" ]]; then
        warn "Nenhum dispositivo pareado ainda."
    else
        echo "$paired"
    fi
}

salvar_dispositivo() {
    local mac="$1"
    local tipo="$2"  # "phone" ou "car"
    local nome="$3"

    # Cria ou atualiza o arquivo de dispositivos
    # Remove entrada existente do mesmo tipo se houver
    touch "$DEVICES_FILE"
    grep -v "^$tipo=" "$DEVICES_FILE" > /tmp/bt_devices_tmp || true
    echo "$tipo=$mac  # $nome" >> /tmp/bt_devices_tmp
    mv /tmp/bt_devices_tmp "$DEVICES_FILE"

    log "Dispositivo salvo: $tipo → $mac ($nome)"
}

parear_dispositivo() {
    local tipo="$1"         # "phone" ou "car"
    local descricao="$2"    # "celular" ou "rádio do carro"

    section "Pareando $descricao"

    info "Prepare o $descricao:"
    if [[ "$tipo" == "phone" ]]; then
        info "  → Abra as configurações de Bluetooth no celular"
        info "  → Deixe o Bluetooth visível/discoverable"
    else
        info "  → Coloque o rádio do carro em modo de pareamento Bluetooth"
    fi
    echo ""
    read -p "Pressione ENTER quando estiver pronto para escanear..."

    # Habilita descoberta
    bluetoothctl discoverable on > /dev/null 2>&1 || true
    bluetoothctl pairable on > /dev/null 2>&1 || true
    bluetoothctl agent on > /dev/null 2>&1 || true
    bluetoothctl default-agent > /dev/null 2>&1 || true

    log "Escaneando dispositivos por 15 segundos..."
    echo ""

    # Escaneia por 15 segundos e captura os dispositivos encontrados
    timeout 15 bluetoothctl scan on 2>/dev/null || true

    echo ""
    echo "Dispositivos encontrados:"
    bluetoothctl devices | head -20
    echo ""

    # Pede o MAC ao usuário
    read -p "Digite o MAC do $descricao (formato AA:BB:CC:DD:EE:FF): " MAC
    MAC="${MAC^^}"  # uppercase

    # Valida formato MAC
    if ! [[ "$MAC" =~ ^([0-9A-F]{2}:){5}[0-9A-F]{2}$ ]]; then
        error "MAC inválido: $MAC"
    fi

    # Tenta obter o nome do dispositivo
    NOME=$(bluetoothctl info "$MAC" 2>/dev/null | grep "Name:" | awk '{print $2}' || echo "$descricao")

    log "Pareando com $MAC ($NOME)..."

    # Para o scan antes de parear
    bluetoothctl scan off > /dev/null 2>&1 || true

    # Pareia
    if bluetoothctl pair "$MAC"; then
        log "Pareado com sucesso!"
    else
        warn "Comando pair retornou erro — pode já estar pareado. Continuando..."
    fi

    # Confia (reconexão automática)
    bluetoothctl trust "$MAC"
    log "Dispositivo marcado como confiável (reconexão automática habilitada)."

    # Conecta
    log "Conectando..."
    if bluetoothctl connect "$MAC"; then
        log "Conectado!"
    else
        warn "Não foi possível conectar agora. O dispositivo reconectará automaticamente na próxima vez."
    fi

    # Salva no arquivo de configuração
    salvar_dispositivo "$MAC" "$tipo" "$NOME"

    echo ""
    log "$descricao pareado: $MAC ($NOME)"
}

configurar_perfis_audio() {
    section "Configurando perfis de áudio"

    # Lê os dispositivos salvos
    if [[ ! -f "$DEVICES_FILE" ]]; then
        warn "Arquivo de dispositivos não encontrado. Pulando configuração de áudio."
        return
    fi

    PHONE_MAC=$(grep "^phone=" "$DEVICES_FILE" 2>/dev/null | cut -d= -f2 | cut -d' ' -f1 || true)
    CAR_MAC=$(grep "^car=" "$DEVICES_FILE" 2>/dev/null | cut -d= -f2 | cut -d' ' -f1 || true)

    if [[ -n "$PHONE_MAC" ]]; then
        log "Configurando celular ($PHONE_MAC) como A2DP source → Rock Pi como sink..."
        # Força perfil A2DP no celular (PipeWire/pactl)
        # O sink do celular é onde o Rock Pi recebe o áudio
        sleep 1
        pactl list cards 2>/dev/null | grep -A5 "$PHONE_MAC" || true
    fi

    if [[ -n "$CAR_MAC" ]]; then
        log "Configurando rádio ($CAR_MAC) como A2DP sink → Rock Pi como source..."
        sleep 1
        pactl list cards 2>/dev/null | grep -A5 "$CAR_MAC" || true
    fi

    log "Perfis configurados."
}

# =============================================================================
# Menu principal
# =============================================================================

echo ""
echo -e "${BLUE}╔══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     Palio-IA — Pareamento Bluetooth  ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════╝${NC}"
echo ""

verificar_bluetooth
listar_dispositivos_pareados

echo ""
echo "O que você quer fazer?"
echo ""
echo "  1) Parear celular (fonte de música)"
echo "  2) Parear rádio do carro (destino de áudio)"
echo "  3) Parear os dois (celular + rádio)"
echo "  4) Ver dispositivos pareados"
echo "  5) Remover um dispositivo"
echo "  6) Sair"
echo ""
read -p "Escolha [1-6]: " OPCAO

case "$OPCAO" in
    1)
        parear_dispositivo "phone" "celular"
        configurar_perfis_audio
        ;;
    2)
        parear_dispositivo "car" "rádio do carro"
        configurar_perfis_audio
        ;;
    3)
        parear_dispositivo "phone" "celular"
        echo ""
        parear_dispositivo "car" "rádio do carro"
        configurar_perfis_audio
        ;;
    4)
        listar_dispositivos_pareados
        echo ""
        if [[ -f "$DEVICES_FILE" ]]; then
            info "Dispositivos do projeto:"
            cat "$DEVICES_FILE"
        fi
        ;;
    5)
        listar_dispositivos_pareados
        echo ""
        read -p "Digite o MAC do dispositivo a remover: " MAC_REMOVE
        MAC_REMOVE="${MAC_REMOVE^^}"
        bluetoothctl remove "$MAC_REMOVE" && log "Dispositivo $MAC_REMOVE removido."
        # Remove do arquivo de configuração
        if [[ -f "$DEVICES_FILE" ]]; then
            grep -v "$MAC_REMOVE" "$DEVICES_FILE" > /tmp/bt_tmp || true
            mv /tmp/bt_tmp "$DEVICES_FILE"
        fi
        ;;
    6)
        log "Saindo."
        exit 0
        ;;
    *)
        error "Opção inválida."
        ;;
esac

# =============================================================================
# Resumo final
# =============================================================================
section "Concluído"

if [[ -f "$DEVICES_FILE" ]]; then
    echo ""
    info "Dispositivos configurados:"
    while IFS= read -r line; do
        [[ -z "$line" || "$line" =~ ^# ]] && continue
        tipo=$(echo "$line" | cut -d= -f1)
        resto=$(echo "$line" | cut -d= -f2)
        mac=$(echo "$resto" | awk '{print $1}')
        nome=$(echo "$resto" | cut -d'#' -f2 | xargs)
        case "$tipo" in
            phone) echo -e "  ${GREEN}Celular${NC}:       $mac  ($nome)" ;;
            car)   echo -e "  ${GREEN}Rádio do carro${NC}: $mac  ($nome)" ;;
        esac
    done < "$DEVICES_FILE"
fi

echo ""
log "Esses dispositivos reconectarão automaticamente sempre que o Rock Pi ligar."
echo ""
