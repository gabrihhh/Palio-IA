"""
modules/bluetooth/audio.py

Controle de volume do sink padrão do PipeWire via pactl.

Pré-requisitos (Linux):
  apt install pipewire pipewire-pulse wireplumber

Em sistemas não-Linux, usa MockVolumeController para desenvolvimento.
"""

import subprocess
import sys
import logging

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
