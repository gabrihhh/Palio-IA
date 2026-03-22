"""
modules/bluetooth/pairing.py

Gerenciador de pareamento Bluetooth por voz.

Fluxo de pareamento (modo descobrível):
─────────────────────────────────────────────────────────────────────────────
MODO PAREAMENTO ("carro modo de pareamento")
  1. Desconecta qualquer dispositivo atual
  2. Coloca o Rock Pi em modo visível e pareável
  3. Fala: "Pronto para parear. Você tem 60 segundos."
  4. Aguarda o celular conectar por iniciativa própria (usuário vai nas
     configurações de BT do celular e conecta ao Rock Pi)
  5. Se conectar dentro de 60s:
     - Salva o dispositivo (sobrescreve o anterior — apenas 1 salvo por vez)
     - Fala: "Dispositivo conectado e salvo."
  6. Se esgotar o tempo:
     - Fala: "Tempo esgotado. Tente novamente."
  7. Desliga modo visível

CONECTAR ("carro conectar")
  1. Lê o dispositivo salvo em data/devices.json
  2. Tenta conectar via bluetoothctl
  3. Se conectar: "Dispositivo conectado."
  4. Se não encontrar: "Não foi possível achar o dispositivo."

─────────────────────────────────────────────────────────────────────────────
Persistência (data/devices.json):
  {
    "devices": [
      {
        "apelido": "Pixel 7",
        "nome_bt": "Pixel 7",
        "mac": "AA:BB:CC:DD:EE:FF",
        "last_connected": "2026-03-22T10:30:00"
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
from dataclasses import dataclass, asdict
from datetime import datetime
from threading import Thread
from typing import Callable

logger = logging.getLogger(__name__)

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEVICES_FILE = os.path.join(_PROJECT_DIR, "data", "devices.json")

PAIRING_TIMEOUT = 60   # segundos aguardando o celular conectar
POLL_INTERVAL = 2      # intervalo de polling para detectar nova conexão


def _is_linux() -> bool:
    return sys.platform.startswith("linux")


# ---------------------------------------------------------------------------
# Estrutura de dados
# ---------------------------------------------------------------------------

@dataclass
class PairedDevice:
    apelido: str        # nome como o dispositivo se anunciou via BT
    nome_bt: str        # nome real do dispositivo BT
    mac: str            # endereço MAC (XX:XX:XX:XX:XX:XX)
    last_connected: str = ""   # ISO 8601

    def touch(self) -> None:
        self.last_connected = datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Persistência
# ---------------------------------------------------------------------------

def _carregar_device() -> PairedDevice | None:
    """Lê data/devices.json e retorna o único dispositivo salvo (ou None)."""
    if not os.path.exists(DEVICES_FILE):
        return None
    try:
        with open(DEVICES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        devices = data.get("devices", [])
        if not devices:
            return None
        d = devices[0]
        d.setdefault("last_connected", "")
        return PairedDevice(**d)
    except Exception as e:
        logger.error("Erro ao carregar devices.json: %s", e)
        return None


def _salvar_device(device: PairedDevice) -> None:
    """Persiste um único dispositivo em data/devices.json (sobrescreve qualquer anterior)."""
    os.makedirs(os.path.dirname(DEVICES_FILE), exist_ok=True)
    try:
        with open(DEVICES_FILE, "w", encoding="utf-8") as f:
            json.dump({"devices": [asdict(device)]}, f, indent=2, ensure_ascii=False)
        logger.info("devices.json salvo: %s (%s).", device.apelido, device.mac)
    except Exception as e:
        logger.error("Erro ao salvar devices.json: %s", e)


# ---------------------------------------------------------------------------
# Controle bluetoothctl
# ---------------------------------------------------------------------------

def _bt_run(commands: list[str], timeout: int = 10) -> str:
    """Executa uma sequência de comandos no bluetoothctl e retorna a saída."""
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
            proc.stdin.write(cmd + "\n")
        proc.stdin.write("quit\n")
        proc.stdin.flush()
        output = proc.stdout.read()
        proc.wait(timeout=timeout)
        return output
    except FileNotFoundError:
        logger.error("bluetoothctl não encontrado.")
        return ""
    except Exception as e:
        logger.error("Erro no bluetoothctl: %s", e)
        return ""


def _bt_set_discoverable(on: bool) -> None:
    """Liga ou desliga o modo visível e pareável do Rock Pi."""
    val = "on" if on else "off"
    _bt_run(["power on", f"discoverable {val}", f"pairable {val}"])
    logger.info("Bluetooth discoverable=%s.", val)


def _bt_disconnect_all() -> None:
    """Desconecta todos os dispositivos atualmente conectados."""
    try:
        result = subprocess.run(
            ["bluetoothctl", "devices", "Connected"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            m = re.search(r"([0-9A-F:]{17})", line)
            if m:
                mac = m.group(1)
                _bt_run([f"disconnect {mac}"])
                logger.info("Desconectou %s.", mac)
    except Exception as e:
        logger.warning("Erro ao desconectar dispositivos: %s", e)


def _bt_get_connected_devices() -> list[dict]:
    """Retorna lista de {mac, nome} dos dispositivos BT atualmente conectados."""
    try:
        result = subprocess.run(
            ["bluetoothctl", "devices", "Connected"],
            capture_output=True, text=True, timeout=5,
        )
        devices = []
        for line in result.stdout.splitlines():
            # Linha típica: "Device AA:BB:CC:DD:EE:FF Nome Do Dispositivo"
            m = re.match(r"Device ([0-9A-F:]{17})\s+(.*)", line.strip())
            if m:
                devices.append({"mac": m.group(1), "nome": m.group(2).strip()})
        return devices
    except Exception as e:
        logger.warning("Erro ao listar dispositivos conectados: %s", e)
        return []


def _bt_connect(mac: str) -> bool:
    """Tenta conectar a um MAC via bluetoothctl. Retorna True se bem-sucedido."""
    output = _bt_run(["power on", f"connect {mac}"], timeout=15)
    success = "Connection successful" in output or "Connected: yes" in output
    logger.info("bt_connect %s → %s.", mac, "ok" if success else "falhou")
    return success


def _bt_trust(mac: str) -> None:
    """Marca o dispositivo como confiável para reconexão automática."""
    _bt_run([f"trust {mac}"])


# ---------------------------------------------------------------------------
# PairingManager
# ---------------------------------------------------------------------------

class PairingManager:
    """
    Gerenciador de pareamento Bluetooth controlado por voz.

    Dois comandos principais:
      - iniciar_modo_parear(): Rock Pi fica visível 60s aguardando o celular conectar
      - conectar():            conecta ao dispositivo salvo

    Integra-se ao Dispatcher via propriedade `ativo`.
    """

    def __init__(self, falar_cb: Callable[[str], None]) -> None:
        self._falar = falar_cb
        self._ativo = False

    @property
    def ativo(self) -> bool:
        """True se o modo de pareamento está em andamento."""
        return self._ativo

    # ------------------------------------------------------------------
    # Comandos principais
    # ------------------------------------------------------------------

    def iniciar_modo_parear(self) -> str:
        """
        Coloca o Rock Pi em modo descobrível e aguarda o celular conectar (60s).
        Roda em thread separada para não bloquear o TTS.
        Retorna string vazia — a thread chama _falar() diretamente.
        """
        if self._ativo:
            return "Já estou em modo pareamento. Aguarde."

        self._ativo = True
        Thread(target=self._executar_pareamento, daemon=True).start()
        return ""

    def conectar(self) -> str:
        """
        Tenta conectar ao dispositivo salvo.
        Retorna a resposta para o TTS.
        """
        device = _carregar_device()
        if device is None:
            return "Não tenho nenhum dispositivo salvo. Diz 'carro modo de pareamento' pra parear um."

        if not _is_linux():
            return "Dispositivo conectado."  # mock

        ok = _bt_connect(device.mac)
        if ok:
            device.touch()
            _salvar_device(device)
            return "Dispositivo conectado."
        return "Não foi possível achar o dispositivo."

    # ------------------------------------------------------------------
    # Fluxo interno de pareamento (roda em thread)
    # ------------------------------------------------------------------

    def _executar_pareamento(self) -> None:
        """Fluxo completo: torna visível → aguarda conexão → salva → desliga visibilidade."""
        try:
            if _is_linux():
                _bt_disconnect_all()
                _bt_set_discoverable(True)
                # Agente sem PIN para aceitar pareamento automaticamente
                subprocess.Popen(
                    ["bluetoothctl", "agent", "NoInputNoOutput"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            self._falar("Pronto para parear. Você tem 60 segundos.")

            device = self._aguardar_conexao(PAIRING_TIMEOUT)

            if device:
                if _is_linux():
                    _bt_trust(device.mac)
                _salvar_device(device)
                self._falar("Dispositivo conectado e salvo.")
                logger.info("Pareamento concluído: %s (%s).", device.apelido, device.mac)
            else:
                self._falar("Tempo esgotado. Tente novamente.")
                logger.info("Pareamento cancelado por timeout.")

        finally:
            if _is_linux():
                _bt_set_discoverable(False)
            self._ativo = False

    def _aguardar_conexao(self, timeout: int) -> PairedDevice | None:
        """
        Faz polling dos dispositivos conectados por até `timeout` segundos.
        Retorna o primeiro novo dispositivo que aparecer, ou None se esgotar.
        """
        if not _is_linux():
            # Mock: simula um celular conectando após 2 segundos
            time.sleep(2)
            return PairedDevice(apelido="Celular Mock", nome_bt="Celular Mock", mac="AA:BB:CC:DD:EE:FF")

        deadline = time.time() + timeout
        macs_antes = {d["mac"] for d in _bt_get_connected_devices()}

        while time.time() < deadline:
            time.sleep(POLL_INTERVAL)
            conectados = _bt_get_connected_devices()
            for d in conectados:
                if d["mac"] not in macs_antes:
                    nome = d["nome"] or d["mac"]
                    return PairedDevice(apelido=nome, nome_bt=nome, mac=d["mac"])

        return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_pairing_manager(falar_cb: Callable[[str], None]) -> PairingManager:
    return PairingManager(falar_cb)
