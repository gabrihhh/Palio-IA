"""
modules/bluetooth/pairing.py

Gerenciador de pareamento Bluetooth por voz.

Dois modos de pareamento:
─────────────────────────────────────────────────────────────────────────────
MODO PAREAR (manual, scan ao vivo)
  1. Usuário diz "Palio, modo parear"
  2. Sistema pergunta: "entrada ou saída?"
  3. Usuário responde
  4. Sistema faz scan BT por ~12 segundos
  5. Anuncia os dispositivos encontrados no ar (ignora os já salvos)
  6. Usuário escolhe o nome pelo que ouviu
  7. Sistema faz pair + trust + connect via bluetoothctl
  8. Salva em data/devices.json marcando last_connected = agora
  9. Confirma: "Gabriel pareado como entrada."

MODO PAREAMENTO AUTOMÁTICO (conecta os salvos)
  1. Usuário diz "Palio, pareamento automático"
  2. Sistema busca o último dispositivo de entrada (sink) e o último de saída (source)
     com base no campo last_connected
  3. Tenta conectar ambos via bluetoothctl
  4. Confirma o resultado: "Gabriel conectado na entrada. Rádio conectado na saída."

─────────────────────────────────────────────────────────────────────────────
Persistência (data/devices.json):
  {
    "devices": [
      {
        "apelido": "Gabriel",
        "nome_bt": "Gabriel",
        "mac": "AA:BB:CC:DD:EE:FF",
        "role": "sink",
        "auto_connect": true,
        "last_connected": "2026-03-04T10:30:00"   ← atualizado a cada conexão
      }
    ]
  }

Em sistemas não-Linux, as chamadas bluetoothctl são simuladas automaticamente.
"""

import json
import logging
import os
import re
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass, asdict, field
from datetime import datetime
from threading import Thread
from typing import Callable

logger = logging.getLogger(__name__)

# Caminho padrão do arquivo de persistência
_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEVICES_FILE = os.path.join(_PROJECT_DIR, "data", "devices.json")

# Duração do scan em segundos
SCAN_DURATION = 12


def _is_linux() -> bool:
    return sys.platform.startswith("linux")


def _normalizar(texto: str) -> str:
    """Remove acentos e converte para minúsculas."""
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    ).lower()


# ---------------------------------------------------------------------------
# Estrutura de dados
# ---------------------------------------------------------------------------

@dataclass
class PairedDevice:
    apelido: str        # nome como o usuário disse por voz
    nome_bt: str        # nome real anunciado pelo dispositivo BT
    mac: str            # endereço MAC  (XX:XX:XX:XX:XX:XX)
    role: str           # "sink" = entrada (celular) | "source" = saída (rádio)
    auto_connect: bool = True
    last_connected: str = ""   # ISO 8601, ex: "2026-03-04T10:30:00" — atualizado a cada conexão

    def role_label(self) -> str:
        return "entrada" if self.role == "sink" else "saída"

    def touch(self) -> None:
        """Atualiza last_connected para agora."""
        self.last_connected = datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Persistência
# ---------------------------------------------------------------------------

def _carregar_devices() -> list[PairedDevice]:
    """Lê data/devices.json e retorna lista de PairedDevice."""
    if not os.path.exists(DEVICES_FILE):
        return []
    try:
        with open(DEVICES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        devices = []
        for d in data.get("devices", []):
            # Compatibilidade com JSONs antigos que não tinham last_connected
            d.setdefault("last_connected", "")
            devices.append(PairedDevice(**d))
        return devices
    except Exception as e:
        logger.error("Erro ao carregar devices.json: %s", e)
        return []


def _salvar_devices(devices: list[PairedDevice]) -> None:
    """Persiste lista de PairedDevice em data/devices.json."""
    os.makedirs(os.path.dirname(DEVICES_FILE), exist_ok=True)
    try:
        with open(DEVICES_FILE, "w", encoding="utf-8") as f:
            json.dump({"devices": [asdict(d) for d in devices]}, f, indent=2, ensure_ascii=False)
        logger.info("devices.json salvo com %d dispositivos.", len(devices))
    except Exception as e:
        logger.error("Erro ao salvar devices.json: %s", e)


# ---------------------------------------------------------------------------
# Controle bluetoothctl
# ---------------------------------------------------------------------------

def _bt_scan(duration: int = SCAN_DURATION) -> dict[str, str]:
    """
    Executa scan Bluetooth por `duration` segundos via bluetoothctl.

    Retorna dict {nome_bt: mac} dos dispositivos encontrados.
    """
    found: dict[str, str] = {}

    try:
        proc = subprocess.Popen(
            ["bluetoothctl"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert proc.stdin and proc.stdout

        # Liga o scan
        proc.stdin.write("power on\n")
        proc.stdin.write("scan on\n")
        proc.stdin.flush()

        deadline = time.time() + duration
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            # Linhas típicas:
            #   [NEW] Device AA:BB:CC:DD:EE:FF Nome Do Dispositivo
            #   [CHG] Device AA:BB:CC:DD:EE:FF Name: Nome Do Dispositivo
            m = re.search(
                r"\[(?:NEW|CHG)\] Device ([0-9A-F:]{17})\s+(?:Name: )?(.+)",
                line,
            )
            if m:
                mac = m.group(1).strip()
                nome = m.group(2).strip()
                # Ignora entradas de alteração que não sejam nomes legíveis
                if nome and not nome.startswith("RSSI") and not nome.startswith("TxPower"):
                    found[nome] = mac
                    logger.debug("Scan encontrou: %s (%s)", nome, mac)

        # Para o scan
        proc.stdin.write("scan off\n")
        proc.stdin.write("quit\n")
        proc.stdin.flush()
        proc.wait(timeout=5)

    except FileNotFoundError:
        logger.error("bluetoothctl não encontrado. Verifique se bluez está instalado.")
    except Exception as e:
        logger.error("Erro durante scan BT: %s", e)

    return found


def _bt_pair_connect(mac: str) -> tuple[bool, str]:
    """
    Faz pair + trust + connect de um MAC via bluetoothctl.

    Retorna (sucesso, mensagem_de_erro_se_houver).
    """
    commands = [
        "power on\n",
        f"pair {mac}\n",
        f"trust {mac}\n",
        f"connect {mac}\n",
        "quit\n",
    ]

    try:
        proc = subprocess.Popen(
            ["bluetoothctl"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert proc.stdin and proc.stdout

        for cmd in commands:
            proc.stdin.write(cmd)
            proc.stdin.flush()
            time.sleep(2)  # aguarda cada operação

        output = proc.stdout.read()
        proc.wait(timeout=30)

        if "Connection successful" in output or "Connected: yes" in output:
            return True, ""
        if "Failed to connect" in output:
            return False, "Falha ao conectar."
        if "not available" in output:
            return False, "Dispositivo não disponível."

        # Assume sucesso se não houve erro explícito
        return True, ""

    except subprocess.TimeoutExpired:
        return False, "Timeout ao parear."
    except FileNotFoundError:
        return False, "bluetoothctl não encontrado."
    except Exception as e:
        return False, str(e)


def _bt_remove(mac: str) -> bool:
    """Remove um dispositivo pareado via bluetoothctl."""
    try:
        result = subprocess.run(
            ["bluetoothctl", "remove", mac],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception as e:
        logger.error("Erro ao remover dispositivo %s: %s", mac, e)
        return False


# ---------------------------------------------------------------------------
# PairingManager — máquina de estados
# ---------------------------------------------------------------------------

class PairingState:
    IDLE = "idle"
    AGUARDANDO_ROLE = "aguardando_role"      # perguntou entrada/saída, aguarda resposta
    ESCANEANDO = "escaneando"                # scan em progresso
    AGUARDANDO_NOME = "aguardando_nome"      # anunciou dispositivos, aguarda escolha
    PAREANDO = "pareando"                    # pair+connect em andamento


class PairingManager:
    """
    Gerenciador de pareamento Bluetooth controlado por voz.

    Integra-se ao Dispatcher: quando o modo de pareamento está ativo,
    o Dispatcher redireciona o texto STT para este manager em vez do LLM.

    Uso típico no Dispatcher:
        if self._pairing.ativo:
            resposta = self._pairing.processar(texto)
        else:
            resposta = self._processar_normal(texto)

    Callbacks:
        falar_cb: função(str) que lê um texto em voz alta
    """

    def __init__(self, falar_cb: Callable[[str], None]) -> None:
        self._falar = falar_cb
        self._estado = PairingState.IDLE
        self._role_pendente: str = ""            # "sink" ou "source"
        self._scan_result: dict[str, str] = {}   # {nome_bt: mac}
        self._nomes_normalizados: dict[str, str] = {}  # {nome_norm: nome_original}
        self._devices: list[PairedDevice] = _carregar_devices()

    # ------------------------------------------------------------------
    # Estado público
    # ------------------------------------------------------------------

    @property
    def ativo(self) -> bool:
        """True se o modo de pareamento está ativo (não está IDLE)."""
        return self._estado != PairingState.IDLE

    def cancelar(self) -> str:
        """Cancela o modo de pareamento e volta ao estado idle."""
        self._estado = PairingState.IDLE
        self._role_pendente = ""
        self._scan_result = {}
        logger.info("Modo pareamento cancelado.")
        return "Pareamento cancelado."

    # ------------------------------------------------------------------
    # Dispositivos salvos
    # ------------------------------------------------------------------

    def listar_dispositivos(self) -> list[PairedDevice]:
        """Retorna a lista de dispositivos salvos."""
        return list(self._devices)

    def remover_dispositivo(self, apelido: str) -> str:
        """Remove um dispositivo pelo apelido (normalizado)."""
        apelido_norm = _normalizar(apelido)
        for i, d in enumerate(self._devices):
            if _normalizar(d.apelido) == apelido_norm:
                mac = d.mac
                nome = d.apelido
                self._devices.pop(i)
                _salvar_devices(self._devices)
                if _is_linux():
                    _bt_remove(mac)
                return f"{nome} removido."
        return f"Não encontrei nenhum dispositivo com esse nome."

    def reconectar_todos(self) -> str:
        """Tenta reconectar todos os dispositivos com auto_connect=True."""
        if not _is_linux():
            return "Reconexão simulada (modo desenvolvimento)."

        auto = [d for d in self._devices if d.auto_connect]
        if not auto:
            return "Nenhum dispositivo configurado para reconexão automática."

        conectados = []
        falhas = []
        for d in auto:
            ok, _ = _bt_pair_connect(d.mac)
            if ok:
                d.touch()
                conectados.append(d.apelido)
            else:
                falhas.append(d.apelido)

        _salvar_devices(self._devices)

        partes = []
        if conectados:
            partes.append(f"{', '.join(conectados)} conectado{'s' if len(conectados) > 1 else ''}.")
        if falhas:
            partes.append(f"Não consegui conectar {', '.join(falhas)}.")
        return " ".join(partes) or "Nenhum dispositivo para reconectar."

    def pareamento_automatico(self) -> str:
        """
        Conecta automaticamente o último dispositivo de entrada (sink) e
        o último dispositivo de saída (source) salvos, baseando-se no
        campo last_connected.

        Chamado pelo Dispatcher ao detectar "pareamento automático".
        """
        # Pega o mais recente de cada role
        ultimo_sink = self._ultimo_por_role("sink")
        ultimo_source = self._ultimo_por_role("source")

        if not ultimo_sink and not ultimo_source:
            return (
                "Não tenho nenhum dispositivo salvo ainda. "
                "Diz 'modo parear' pra eu aprender um novo."
            )

        partes_ok = []
        partes_fail = []

        for device in filter(None, [ultimo_sink, ultimo_source]):
            label = device.role_label()
            if _is_linux():
                ok, _ = _bt_pair_connect(device.mac)
            else:
                ok = True  # mock

            if ok:
                device.touch()
                partes_ok.append(f"{device.apelido} na {label}")
            else:
                partes_fail.append(f"{device.apelido} na {label}")

        _salvar_devices(self._devices)

        resposta = []
        if partes_ok:
            resp = ", ".join(partes_ok)
            resposta.append(f"{resp} conectado{'s' if len(partes_ok) > 1 else ''}.")
        if partes_fail:
            resp = ", ".join(partes_fail)
            resposta.append(f"Não consegui conectar {resp}.")

        if not ultimo_sink:
            resposta.append("Não tenho dispositivo de entrada salvo.")
        if not ultimo_source:
            resposta.append("Não tenho dispositivo de saída salvo.")

        return " ".join(resposta)

    def _ultimo_por_role(self, role: str) -> PairedDevice | None:
        """
        Retorna o dispositivo com a role especificada que foi conectado
        mais recentemente (maior last_connected). Se nenhum tiver
        last_connected preenchido, retorna o último da lista.
        """
        candidatos = [d for d in self._devices if d.role == role]
        if not candidatos:
            return None
        # Ordena por last_connected (string ISO 8601 ordena lexicograficamente)
        com_data = [d for d in candidatos if d.last_connected]
        if com_data:
            return max(com_data, key=lambda d: d.last_connected)
        # Fallback: último adicionado
        return candidatos[-1]

    # ------------------------------------------------------------------
    # Máquina de estados — entry point
    # ------------------------------------------------------------------

    def iniciar_modo_parear(self) -> str:
        """
        Inicia o fluxo de pareamento.
        Chamado pelo Dispatcher quando detecta o comando "modo parear".
        """
        if self._estado != PairingState.IDLE:
            return "Já estou no modo pareamento. Pode falar."

        self._estado = PairingState.AGUARDANDO_ROLE
        logger.info("Modo pareamento iniciado — aguardando role.")
        return "Certo. Esse dispositivo vai ser de entrada, como um celular, ou de saída, como o rádio?"

    def processar(self, texto: str) -> str:
        """
        Processa a resposta do usuário de acordo com o estado atual.

        Deve ser chamado pelo Dispatcher sempre que `self.ativo` for True.
        """
        texto_norm = _normalizar(texto)

        # Cancelamento universal
        if any(p in texto_norm for p in ["cancela", "cancel", "sair", "para", "desiste"]):
            return self.cancelar()

        if self._estado == PairingState.AGUARDANDO_ROLE:
            return self._processar_role(texto_norm)

        if self._estado == PairingState.AGUARDANDO_NOME:
            return self._processar_escolha_nome(texto_norm)

        # Estados de transição (escaneando, pareando) — não há input esperado
        return "Aguarde, estou processando."

    # ------------------------------------------------------------------
    # Passos internos
    # ------------------------------------------------------------------

    def _processar_role(self, texto_norm: str) -> str:
        """Passo 1: interpreta entrada/saída e inicia o scan."""
        if any(p in texto_norm for p in ["entrada", "celular", "telefone", "sink"]):
            self._role_pendente = "sink"
            label = "entrada"
        elif any(p in texto_norm for p in ["saida", "radio", "caixa", "source", "carro"]):
            self._role_pendente = "source"
            label = "saída"
        else:
            return "Não entendi. Fala 'entrada' para celular ou 'saída' para rádio."

        self._estado = PairingState.ESCANEANDO
        logger.info("Role definida: %s. Iniciando scan...", self._role_pendente)

        # Scan em thread separada para não bloquear o TTS
        self._falar(
            f"Certo, vou procurar dispositivos de {label}. "
            f"Aguarde uns {SCAN_DURATION} segundos enquanto escaneo."
        )
        Thread(target=self._executar_scan, daemon=True).start()

        # Retorna string vazia — o scan vai chamar _falar por conta própria
        return ""

    def _executar_scan(self) -> None:
        """Executa o scan BT e anuncia os resultados (roda em thread)."""
        if _is_linux():
            resultado = _bt_scan(SCAN_DURATION)
        else:
            # Mock para desenvolvimento
            resultado = {
                "Gabriel": "AA:BB:CC:DD:EE:FF",
                "Rádio Palio": "11:22:33:44:55:66",
                "Caixa JBL": "77:88:99:AA:BB:CC",
            }
            time.sleep(2)

        # Remove os dispositivos já salvos do resultado do scan
        macs_salvos = {d.mac for d in self._devices}
        resultado = {nome: mac for nome, mac in resultado.items() if mac not in macs_salvos}

        self._scan_result = resultado
        self._nomes_normalizados = {_normalizar(n): n for n in resultado}
        self._estado = PairingState.AGUARDANDO_NOME

        if not resultado:
            self._falar(
                "Não encontrei nenhum dispositivo novo. "
                "Certifique-se de que o Bluetooth do dispositivo está ligado e visível."
            )
            self._estado = PairingState.IDLE
            return

        nomes = list(resultado.keys())
        if len(nomes) == 1:
            lista = nomes[0]
        elif len(nomes) == 2:
            lista = f"{nomes[0]} e {nomes[1]}"
        else:
            lista = ", ".join(nomes[:-1]) + f" e {nomes[-1]}"

        self._falar(
            f"Encontrei {len(nomes)} dispositivo{'s' if len(nomes) > 1 else ''}: "
            f"{lista}. Qual você quer parear?"
        )

    def _processar_escolha_nome(self, texto_norm: str) -> str:
        """Passo 3: identifica qual dispositivo o usuário escolheu e faz o pair."""
        # Tenta encontrar o nome mais parecido na lista de scan
        nome_bt, mac = self._encontrar_dispositivo(texto_norm)

        if not nome_bt or not mac:
            nomes = list(self._scan_result.keys())
            lista = ", ".join(nomes) if nomes else "nenhum"
            return f"Não encontrei esse nome. Os dispositivos disponíveis são: {lista}. Qual você quer?"

        # Verifica se já está pareado com esse MAC
        existente = next((d for d in self._devices if d.mac == mac), None)
        if existente:
            # Atualiza a role se necessário e toca last_connected
            existente.role = self._role_pendente
            existente.touch()
            _salvar_devices(self._devices)
            return f"{existente.apelido} reconectado como {existente.role_label()}."

        self._estado = PairingState.PAREANDO
        apelido = nome_bt  # usa o nome BT como apelido inicial

        self._falar(f"Pareando com {nome_bt}. Aguarde.")

        if _is_linux():
            ok, erro = _bt_pair_connect(mac)
        else:
            ok, erro = True, ""  # mock

        if not ok:
            self._estado = PairingState.IDLE
            return f"Não consegui parear com {nome_bt}. {erro}"

        # Salva o dispositivo
        device = PairedDevice(
            apelido=apelido,
            nome_bt=nome_bt,
            mac=mac,
            role=self._role_pendente,
            auto_connect=True,
        )
        device.touch()
        self._devices.append(device)
        _salvar_devices(self._devices)

        self._estado = PairingState.IDLE
        self._scan_result = {}
        self._role_pendente = ""

        label = device.role_label()
        logger.info("Dispositivo pareado: %s (%s) como %s.", nome_bt, mac, label)
        return f"{nome_bt} pareado com sucesso como {label}."

    def _encontrar_dispositivo(self, texto_norm: str) -> tuple[str, str]:
        """
        Encontra o dispositivo cujo nome normalizado está contido no texto do usuário.

        Retorna (nome_bt_original, mac) ou ("", "") se não encontrado.
        """
        # Busca exata por substring normalizada
        for nome_norm, nome_original in self._nomes_normalizados.items():
            if nome_norm in texto_norm or texto_norm in nome_norm:
                mac = self._scan_result[nome_original]
                return nome_original, mac

        # Fallback: busca por cada palavra do texto nos nomes
        palavras = texto_norm.split()
        for palavra in palavras:
            if len(palavra) < 3:
                continue
            for nome_norm, nome_original in self._nomes_normalizados.items():
                if palavra in nome_norm:
                    mac = self._scan_result[nome_original]
                    return nome_original, mac

        return "", ""


# ---------------------------------------------------------------------------
# Mock para desenvolvimento no Windows
# ---------------------------------------------------------------------------

class MockPairingManager(PairingManager):
    """
    Subclasse de PairingManager que funciona no Windows para desenvolvimento.
    Toda a lógica de estado é real; apenas as chamadas bluetoothctl são simuladas.
    """

    def __init__(self, falar_cb: Callable[[str], None]) -> None:
        super().__init__(falar_cb)
        logger.info("MockPairingManager ativo (modo desenvolvimento).")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_pairing_manager(falar_cb: Callable[[str], None]) -> PairingManager:
    """
    Factory: retorna PairingManager em qualquer sistema.
    O mock de bluetoothctl já está embutido nos métodos internos (_bt_scan etc.)
    quando não está em Linux.
    """
    return PairingManager(falar_cb)
