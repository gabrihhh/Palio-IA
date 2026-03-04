"""
modules/bluetooth/audio_duck.py

Duck de áudio: reduz o volume do sink de saída quando a wake word é detectada
e restaura ao volume original após o TTS terminar.

Comportamento:
  1. on_wake_word() → lê volume atual → salva → aplica DUCK_VOLUME instantaneamente
  2. on_done()      → restaura o volume salvo

Em sistemas não-Linux, usa MockAudioDuck que apenas loga as operações.

Uso em main.py:
    duck = create_audio_duck()
    duck.on_wake_word()
    falar(resposta)
    duck.on_done()
"""

import subprocess
import sys
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Volume reduzido durante escuta/resposta (% de 0-100)
DUCK_VOLUME = 20

# Sink padrão do PipeWire a ser controlado.
# "@DEFAULT_SINK@" funciona sem precisar saber o nome exato do dispositivo.
DEFAULT_SINK = "@DEFAULT_SINK@"


def _is_linux() -> bool:
    return sys.platform.startswith("linux")


def _run(cmd: list[str]) -> tuple[int, str]:
    """Executa um comando e retorna (returncode, saída combinada)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3,
        )
        return result.returncode, (result.stdout + result.stderr).strip()
    except FileNotFoundError:
        return -1, f"Comando não encontrado: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -1, "Timeout"
    except Exception as e:
        return -1, str(e)


def _get_volume(sink: str) -> Optional[int]:
    """Lê o volume atual do sink (0-100). Retorna None em caso de erro."""
    code, out = _run(["pactl", "get-sink-volume", sink])
    if code != 0:
        logger.warning("Não foi possível ler volume de '%s': %s", sink, out)
        return None
    for token in out.split():
        if token.endswith("%"):
            try:
                return int(token.rstrip("%"))
            except ValueError:
                pass
    return None


def _set_volume(sink: str, percent: int) -> bool:
    """Define o volume do sink instantaneamente (0-100)."""
    percent = max(0, min(100, percent))
    code, out = _run(["pactl", "set-sink-volume", sink, f"{percent}%"])
    if code != 0:
        logger.warning("Erro ao definir volume de '%s' para %d%%: %s", sink, percent, out)
        return False
    return True


class AudioDuck:
    """
    Controla o duck de áudio via pactl/PipeWire.

    Reduz o volume ao detectar a wake word e restaura após o TTS terminar.
    """

    def __init__(self, sink: str = DEFAULT_SINK, duck_volume: int = DUCK_VOLUME) -> None:
        self._sink = sink
        self._duck_volume = duck_volume
        self._original_volume: Optional[int] = None

    def on_wake_word(self) -> None:
        """
        Chamado imediatamente ao detectar a wake word.
        Salva o volume atual e aplica o duck instantaneamente.
        """
        current = _get_volume(self._sink)
        if current is None:
            logger.warning("AudioDuck: não foi possível ler volume — duck ignorado.")
            return

        self._original_volume = current
        logger.debug("AudioDuck: volume salvo = %d%%. Aplicando duck → %d%%.", current, self._duck_volume)
        _set_volume(self._sink, self._duck_volume)

    def on_done(self) -> None:
        """
        Chamado após o TTS terminar.
        Restaura o volume ao valor original.
        """
        if self._original_volume is None:
            logger.debug("AudioDuck: nenhum volume salvo para restaurar.")
            return

        logger.debug("AudioDuck: restaurando volume → %d%%.", self._original_volume)
        _set_volume(self._sink, self._original_volume)
        self._original_volume = None


class MockAudioDuck:
    """
    Mock do AudioDuck para desenvolvimento em Windows / sistemas sem PipeWire.
    Apenas loga as operações sem fazer nada real.
    """

    def on_wake_word(self) -> None:
        logger.info("[MOCK] AudioDuck: duck aplicado (volume simulado → %d%%).", DUCK_VOLUME)

    def on_done(self) -> None:
        logger.info("[MOCK] AudioDuck: volume restaurado (simulado).")


def create_audio_duck(
    sink: str = DEFAULT_SINK,
    duck_volume: int = DUCK_VOLUME,
) -> AudioDuck | MockAudioDuck:
    """
    Factory: retorna AudioDuck em Linux, MockAudioDuck em outros sistemas.

    Args:
        sink:        Nome do sink PipeWire. Padrão: "@DEFAULT_SINK@".
        duck_volume: Volume reduzido durante escuta/resposta (0-100). Padrão: 20.
    """
    if _is_linux():
        return AudioDuck(sink=sink, duck_volume=duck_volume)
    return MockAudioDuck()
