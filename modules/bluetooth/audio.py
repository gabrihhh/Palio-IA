"""
modules/bluetooth/audio.py

Gerenciamento de áudio Bluetooth via PipeWire/pactl.

Responsabilidades:
  - Verificar dispositivos Bluetooth conectados (A2DP sink/source)
  - Controlar volume do sink de saída (para o rádio)
  - Controlar volume do sink de entrada (do celular)
  - Listar dispositivos PipeWire ativos

Arquitetura de áudio:
  [Celular] --A2DP source--> [Rock Pi (A2DP sink)] --PipeWire loopback--> [A2DP source] --> [Rádio]

Pré-requisitos (Linux):
  apt install pipewire pipewire-pulse wireplumber libspa-0.2-bluetooth

Em sistemas não-Linux, usa MockAudioController para desenvolvimento.
"""

import subprocess
import sys
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


def _is_linux() -> bool:
    return sys.platform.startswith("linux")


def _run(cmd: list[str]) -> tuple[int, str]:
    """Executa um comando e retorna (returncode, stdout+stderr combinados)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode, (result.stdout + result.stderr).strip()
    except FileNotFoundError:
        return -1, f"Comando não encontrado: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -1, f"Timeout ao executar: {' '.join(cmd)}"
    except Exception as e:
        return -1, str(e)


@dataclass
class BTDevice:
    """Representa um dispositivo Bluetooth conectado ao PipeWire."""

    name: str
    mac: str
    role: str  # "sink" (entrada do celular) ou "source" (saída para o rádio)
    pactl_name: str  # nome interno do pactl/PipeWire
    volume_percent: int = 0
    connected: bool = True


@dataclass
class AudioStatus:
    """Estado geral do áudio Bluetooth."""

    devices: list[BTDevice] = field(default_factory=list)
    loopback_active: bool = False
    pipewire_running: bool = False


class BluetoothAudioController:
    """
    Controla o áudio Bluetooth via PipeWire/pactl.

    Permite verificar dispositivos conectados, ajustar volume e checar
    se o loopback (celular → rádio) está ativo.

    Requer Linux com PipeWire instalado e configurado pelo bluetooth_config.sh.
    """

    def __init__(self) -> None:
        self._available = False
        self._check_pipewire()

    def _check_pipewire(self) -> None:
        """Verifica se PipeWire está rodando."""
        if not _is_linux():
            logger.warning(
                "BluetoothAudioController: sistema não é Linux. "
                "Use MockAudioController para desenvolvimento."
            )
            return

        code, out = _run(["pactl", "info"])
        if code == 0 and "PipeWire" in out:
            self._available = True
            logger.info("PipeWire detectado e disponível.")
        else:
            logger.warning(
                f"PipeWire não detectado via pactl. "
                f"Verifique se o serviço está rodando. Saída: {out}"
            )

    @property
    def available(self) -> bool:
        return self._available

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> AudioStatus:
        """
        Retorna o estado atual do áudio Bluetooth.

        Inclui lista de dispositivos BT conectados, status do loopback
        e disponibilidade do PipeWire.
        """
        status = AudioStatus(pipewire_running=self._available)

        if not self._available:
            return status

        status.devices = self._list_bt_devices()
        status.loopback_active = self._is_loopback_active()

        return status

    def _list_bt_devices(self) -> list[BTDevice]:
        """Lista dispositivos Bluetooth conectados como sinks/sources no PipeWire."""
        devices: list[BTDevice] = []

        # Obtém todos os sinks (saídas de áudio — inclui A2DP sink = celular enviando, e A2DP source = rádio recebendo)
        code, out = _run(["pactl", "list", "sinks"])
        if code == 0:
            devices.extend(self._parse_pactl_sinks(out))

        # Obtém todas as sources (entradas de áudio — microfone, loopback monitor, etc.)
        code, out = _run(["pactl", "list", "sources"])
        if code == 0:
            devices.extend(self._parse_pactl_sources(out))

        return devices

    def _parse_pactl_sinks(self, output: str) -> list[BTDevice]:
        """Extrai dispositivos BT do output de `pactl list sinks`."""
        devices = []
        current: dict = {}

        for line in output.splitlines():
            line = line.strip()
            if line.startswith("Name:"):
                current["name"] = line.split(":", 1)[1].strip()
            elif line.startswith("Description:"):
                current["description"] = line.split(":", 1)[1].strip()
            elif "Volume:" in line and "%" in line:
                # Extrai volume médio: "front-left: ... 85%   front-right: ... 85%"
                parts = [p for p in line.split() if p.endswith("%")]
                if parts:
                    try:
                        current["volume"] = int(parts[0].rstrip("%"))
                    except ValueError:
                        current["volume"] = 0
            elif line == "" and current.get("name"):
                # Fim do bloco — adiciona se for Bluetooth
                name = current.get("name", "")
                desc = current.get("description", "")
                if "bluez" in name.lower() or "bluetooth" in desc.lower():
                    mac = self._extract_mac(name)
                    devices.append(
                        BTDevice(
                            name=desc or name,
                            mac=mac,
                            role="source",  # sink do PipeWire = recebe áudio = saída para o rádio
                            pactl_name=name,
                            volume_percent=current.get("volume", 0),
                        )
                    )
                current = {}

        return devices

    def _parse_pactl_sources(self, output: str) -> list[BTDevice]:
        """Extrai dispositivos BT do output de `pactl list sources`."""
        devices = []
        current: dict = {}

        for line in output.splitlines():
            line = line.strip()
            if line.startswith("Name:"):
                current["name"] = line.split(":", 1)[1].strip()
            elif line.startswith("Description:"):
                current["description"] = line.split(":", 1)[1].strip()
            elif "Volume:" in line and "%" in line:
                parts = [p for p in line.split() if p.endswith("%")]
                if parts:
                    try:
                        current["volume"] = int(parts[0].rstrip("%"))
                    except ValueError:
                        current["volume"] = 0
            elif line == "" and current.get("name"):
                name = current.get("name", "")
                desc = current.get("description", "")
                # Ignora monitores de loopback e microfone virtual — só dispositivos BT reais
                if (
                    ("bluez" in name.lower() or "bluetooth" in desc.lower())
                    and ".monitor" not in name
                ):
                    mac = self._extract_mac(name)
                    devices.append(
                        BTDevice(
                            name=desc or name,
                            mac=mac,
                            role="sink",  # source do PipeWire = captura áudio = entrada do celular
                            pactl_name=name,
                            volume_percent=current.get("volume", 0),
                        )
                    )
                current = {}

        return devices

    def _extract_mac(self, pactl_name: str) -> str:
        """Extrai o endereço MAC do nome interno do pactl (ex: bluez_sink.AA_BB_CC_DD_EE_FF)."""
        # Nomes típicos: bluez_sink.AA_BB_CC_DD_EE_FF.a2dp_sink
        parts = pactl_name.split(".")
        for part in parts:
            if len(part) == 17 and part.count("_") == 5:
                return part.replace("_", ":")
        return ""

    def _is_loopback_active(self) -> bool:
        """Verifica se o módulo de loopback PipeWire (celular→rádio) está ativo."""
        code, out = _run(["pactl", "list", "modules"])
        if code != 0:
            return False
        # O bluetooth_config.sh cria um loopback com description="palio-bt-loopback"
        return "palio-bt-loopback" in out or "module-loopback" in out

    # ------------------------------------------------------------------
    # Controle de volume
    # ------------------------------------------------------------------

    def set_volume(self, pactl_sink_name: str, percent: int) -> bool:
        """
        Define o volume de um sink pelo nome interno do pactl.

        Args:
            pactl_sink_name: nome interno (ex: bluez_sink.AA_BB_CC_DD_EE_FF.a2dp_sink)
            percent: volume de 0 a 100

        Returns:
            True se bem-sucedido.
        """
        if not self._available:
            logger.warning("PipeWire não disponível. set_volume ignorado.")
            return False

        percent = max(0, min(100, percent))
        code, out = _run(["pactl", "set-sink-volume", pactl_sink_name, f"{percent}%"])
        if code == 0:
            logger.info(f"Volume de '{pactl_sink_name}' definido para {percent}%.")
            return True
        else:
            logger.error(f"Erro ao definir volume de '{pactl_sink_name}': {out}")
            return False

    def set_volume_by_role(self, role: str, percent: int) -> bool:
        """
        Define o volume de todos os dispositivos BT com o papel especificado.

        Args:
            role: "sink" (entrada do celular) ou "source" (saída para o rádio)
            percent: volume de 0 a 100

        Returns:
            True se ao menos um dispositivo foi ajustado.
        """
        devices = self._list_bt_devices()
        targets = [d for d in devices if d.role == role]

        if not targets:
            logger.warning(f"Nenhum dispositivo BT com role='{role}' encontrado.")
            return False

        success = False
        for device in targets:
            if self.set_volume(device.pactl_name, percent):
                success = True

        return success

    def get_volume(self, pactl_sink_name: str) -> int:
        """
        Retorna o volume atual de um sink (0-100). Retorna -1 em caso de erro.
        """
        if not self._available:
            return -1

        code, out = _run(["pactl", "get-sink-volume", pactl_sink_name])
        if code != 0:
            logger.warning(f"Erro ao obter volume de '{pactl_sink_name}': {out}")
            return -1

        # Saída típica: "Volume: front-left: 65536 / 100% / 0.00 dB, ..."
        for part in out.split():
            if part.endswith("%"):
                try:
                    return int(part.rstrip("%"))
                except ValueError:
                    pass

        return -1

    # ------------------------------------------------------------------
    # Reconexão
    # ------------------------------------------------------------------

    def reconnect_devices(self) -> bool:
        """
        Dispara o script de reconexão Bluetooth gerado pelo bluetooth_config.sh.

        Útil para reconectar após o rádio do carro ser ligado.
        """
        import os

        project_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        reconnect_script = os.path.join(project_dir, "scripts", "bt_reconnect.sh")

        if not os.path.exists(reconnect_script):
            logger.warning(
                f"Script de reconexão não encontrado: {reconnect_script}. "
                "Execute bluetooth_config.sh primeiro."
            )
            return False

        code, out = _run(["bash", reconnect_script])
        if code == 0:
            logger.info("Reconexão Bluetooth iniciada.")
            return True
        else:
            logger.error(f"Erro ao reconectar Bluetooth: {out}")
            return False


# =============================================================================
# Mock para desenvolvimento no Windows
# =============================================================================


class MockAudioController:
    """
    Implementação mock do BluetoothAudioController para desenvolvimento
    em sistemas sem PipeWire/Linux (ex: Windows).

    Simula os mesmos métodos sem fazer nada de verdade.
    """

    def __init__(self) -> None:
        self._volumes: dict[str, int] = {
            "bluez_sink.AA_BB_CC_DD_EE_FF.a2dp_sink": 80,
            "bluez_source.11_22_33_44_55_66.a2dp_source": 75,
        }
        logger.info("MockAudioController ativo (modo desenvolvimento).")

    @property
    def available(self) -> bool:
        return True

    def get_status(self) -> AudioStatus:
        return AudioStatus(
            pipewire_running=True,
            loopback_active=True,
            devices=[
                BTDevice(
                    name="Mock Celular",
                    mac="AA:BB:CC:DD:EE:FF",
                    role="sink",
                    pactl_name="bluez_source.AA_BB_CC_DD_EE_FF.a2dp_source",
                    volume_percent=75,
                ),
                BTDevice(
                    name="Mock Rádio",
                    mac="11:22:33:44:55:66",
                    role="source",
                    pactl_name="bluez_sink.11_22_33_44_55_66.a2dp_sink",
                    volume_percent=80,
                ),
            ],
        )

    def set_volume(self, pactl_sink_name: str, percent: int) -> bool:
        self._volumes[pactl_sink_name] = percent
        logger.info(f"[MOCK] Volume de '{pactl_sink_name}' → {percent}%")
        return True

    def set_volume_by_role(self, role: str, percent: int) -> bool:
        logger.info(f"[MOCK] Volume role='{role}' → {percent}%")
        return True

    def get_volume(self, pactl_sink_name: str) -> int:
        return self._volumes.get(pactl_sink_name, 80)

    def reconnect_devices(self) -> bool:
        logger.info("[MOCK] Reconexão Bluetooth simulada.")
        return True


# =============================================================================
# Factory
# =============================================================================


def create_audio_controller() -> BluetoothAudioController | MockAudioController:
    """
    Factory: retorna BluetoothAudioController em Linux, MockAudioController em outros sistemas.
    """
    if _is_linux():
        return BluetoothAudioController()
    return MockAudioController()


# =============================================================================
# VolumeController — controle de volume por voz (escala 1-10)
# =============================================================================


class VolumeController:
    """
    Controla o volume do sink padrão do PipeWire via pactl.

    Opera sempre em @DEFAULT_SINK@ para não depender do nome exato
    do dispositivo Bluetooth conectado.

    Escala pública: 1-10 (steps de 10%). Internamente usa 0-100%.
    """

    STEP_PERCENT: int = 10
    _SINK: str = "@DEFAULT_SINK@"

    def get_percent(self) -> int:
        """Retorna o volume atual em % (0-100). Retorna -1 em erro."""
        code, out = _run(["pactl", "get-sink-volume", self._SINK])
        if code != 0:
            logger.warning("VolumeController: erro ao ler volume: %s", out)
            return -1
        for token in out.split():
            if token.endswith("%"):
                try:
                    return int(token.rstrip("%"))
                except ValueError:
                    pass
        return -1

    def set_percent(self, percent: int) -> bool:
        """Define volume absoluto (0-100%). Clampeia automaticamente."""
        percent = max(0, min(100, percent))
        code, out = _run(["pactl", "set-sink-volume", self._SINK, f"{percent}%"])
        if code == 0:
            logger.info("VolumeController: volume → %d%%", percent)
            return True
        logger.error("VolumeController: falha ao definir volume: %s", out)
        return False

    def set_step(self, step: int) -> bool:
        """Define volume pela escala 1-10. step=5 → 50%."""
        return self.set_percent(max(1, min(10, step)) * self.STEP_PERCENT)

    def aumentar(self) -> int:
        """Sobe 1 step (10%). Retorna o novo % ou -1 em erro."""
        atual = self.get_percent()
        if atual < 0:
            return -1
        novo = min(100, atual + self.STEP_PERCENT)
        return novo if self.set_percent(novo) else -1

    def diminuir(self) -> int:
        """Desce 1 step (10%). Retorna o novo % ou -1 em erro."""
        atual = self.get_percent()
        if atual < 0:
            return -1
        novo = max(0, atual - self.STEP_PERCENT)
        return novo if self.set_percent(novo) else -1


class MockVolumeController:
    """Mock do VolumeController para desenvolvimento sem PipeWire."""

    STEP_PERCENT: int = 10

    def __init__(self) -> None:
        self._percent: int = 50
        logger.info("MockVolumeController ativo (modo desenvolvimento).")

    def get_percent(self) -> int:
        return self._percent

    def set_percent(self, percent: int) -> bool:
        self._percent = max(0, min(100, percent))
        logger.info("[MOCK] Volume → %d%%", self._percent)
        return True

    def set_step(self, step: int) -> bool:
        return self.set_percent(max(1, min(10, step)) * self.STEP_PERCENT)

    def aumentar(self) -> int:
        novo = min(100, self._percent + self.STEP_PERCENT)
        self.set_percent(novo)
        return self._percent

    def diminuir(self) -> int:
        novo = max(0, self._percent - self.STEP_PERCENT)
        self.set_percent(novo)
        return self._percent


def create_volume_controller() -> VolumeController | MockVolumeController:
    """Factory: VolumeController em Linux, MockVolumeController nos demais."""
    if _is_linux():
        return VolumeController()
    return MockVolumeController()
