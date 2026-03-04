"""
modules/bluetooth/music.py

Controle de música via Bluetooth AVRCP usando bluez + dbus.

Funciona em Linux (Rock Pi 4B / Ubuntu 22.04).
Em outros sistemas, usa MockBluetoothController para desenvolvimento.

Arquitetura de áudio:
  [Celular] --A2DP source--> [Rock Pi (A2DP sink)] --mistura TTS--> [A2DP source] --> [Rádio do carro]

Controle de música:
  Rock Pi envia comandos AVRCP para o celular via bluez DBus.

Pré-requisitos (Linux):
  sudo apt install bluez bluez-utils python3-dbus
  pip install dbus-python

Setup Bluetooth (feito uma vez no terminal):
  bluetoothctl
    power on
    agent on
    default-agent
    scan on
    pair <MAC_CELULAR>
    trust <MAC_CELULAR>
    connect <MAC_CELULAR>
"""

import subprocess
import sys
import logging

logger = logging.getLogger(__name__)

# Constantes AVRCP (DBus bluez)
BLUEZ_SERVICE = "org.bluez"
MEDIA_PLAYER_IFACE = "org.bluez.MediaPlayer1"
DBUS_PROPERTIES_IFACE = "org.freedesktop.DBus.Properties"
DBUS_OBJECT_MANAGER_IFACE = "org.freedesktop.DBus.ObjectManager"


def _is_linux() -> bool:
    return sys.platform.startswith("linux")


class BluetoothMusicController:
    """
    Controla o player de música do celular conectado via Bluetooth AVRCP.

    Usa DBus + bluez para enviar comandos AVRCP ao dispositivo pareado.
    Requer Linux com bluez instalado e dispositivo conectado.
    """

    def __init__(self) -> None:
        self._player = None  # proxy DBus para o MediaPlayer1
        self._bus = None
        self._connected = False
        self._connect()

    def _connect(self) -> None:
        """Conecta ao DBus e localiza o MediaPlayer1 do dispositivo pareado."""
        if not _is_linux():
            logger.warning(
                "BluetoothMusicController: sistema não é Linux. "
                "Bluetooth AVRCP não disponível. Use MockBluetoothController para dev."
            )
            return

        try:
            import dbus  # type: ignore[import]

            self._bus = dbus.SystemBus()
            manager = dbus.Interface(
                self._bus.get_object(BLUEZ_SERVICE, "/"),
                DBUS_OBJECT_MANAGER_IFACE,
            )

            objects = manager.GetManagedObjects()
            player_path = None

            for path, interfaces in objects.items():
                if MEDIA_PLAYER_IFACE in interfaces:
                    player_path = path
                    break

            if player_path is None:
                logger.error(
                    "Nenhum MediaPlayer1 encontrado via bluez. "
                    "Verifique se o celular está conectado via Bluetooth."
                )
                return

            self._player = dbus.Interface(
                self._bus.get_object(BLUEZ_SERVICE, player_path),
                MEDIA_PLAYER_IFACE,
            )
            self._connected = True
            logger.info(f"Bluetooth AVRCP conectado: {player_path}")

        except ImportError:
            logger.error(
                "dbus-python não instalado. "
                "Execute: pip install dbus-python  (ou: apt install python3-dbus)"
            )
        except Exception as e:
            logger.error(f"Erro ao conectar ao AVRCP via DBus: {e}")

    @property
    def connected(self) -> bool:
        return self._connected

    def _send_command(self, command: str) -> bool:
        """Envia um comando AVRCP ao player. Retorna True se bem-sucedido."""
        if not self._connected or self._player is None:
            logger.warning(f"AVRCP não conectado. Comando '{command}' ignorado.")
            return False
        try:
            getattr(self._player, command)()
            logger.info(f"AVRCP: {command} enviado.")
            return True
        except Exception as e:
            logger.error(f"Erro ao enviar AVRCP '{command}': {e}")
            return False

    def play(self) -> bool:
        """Retoma a reprodução."""
        return self._send_command("Play")

    def pause(self) -> bool:
        """Pausa a reprodução."""
        return self._send_command("Pause")

    def next_track(self) -> bool:
        """Avança para a próxima faixa."""
        return self._send_command("Next")

    def previous_track(self) -> bool:
        """Volta para a faixa anterior."""
        return self._send_command("Previous")

    def get_track_info(self) -> dict:
        """
        Retorna informações da faixa atual (título, artista, álbum).
        Retorna dict vazio se não disponível.
        """
        if not self._connected or self._player is None:
            return {}
        assert self._bus is not None
        try:
            import dbus  # type: ignore[import]

            props = dbus.Interface(
                self._bus.get_object(
                    BLUEZ_SERVICE,
                    self._player.object_path,  # type: ignore[attr-defined]
                ),
                DBUS_PROPERTIES_IFACE,
            )
            track = props.Get(MEDIA_PLAYER_IFACE, "Track")
            return {
                "title": str(track.get("Title", "")),
                "artist": str(track.get("Artist", "")),
                "album": str(track.get("Album", "")),
            }
        except Exception as e:
            logger.warning(f"Erro ao obter info da faixa: {e}")
            return {}

    def get_status(self) -> str:
        """
        Retorna o status atual do player: 'playing', 'paused', 'stopped' ou 'unknown'.
        """
        if not self._connected or self._player is None:
            return "unknown"
        assert self._bus is not None
        try:
            import dbus  # type: ignore[import]

            props = dbus.Interface(
                self._bus.get_object(
                    BLUEZ_SERVICE,
                    self._player.object_path,  # type: ignore[attr-defined]
                ),
                DBUS_PROPERTIES_IFACE,
            )
            status = props.Get(MEDIA_PLAYER_IFACE, "Status")
            return str(status).lower()
        except Exception as e:
            logger.warning(f"Erro ao obter status do player: {e}")
            return "unknown"


class MockBluetoothController:
    """
    Implementação mock do BluetoothMusicController para desenvolvimento
    em sistemas sem Bluetooth/Linux (ex: Windows).

    Simula os mesmos métodos sem fazer nada de verdade.
    """

    def __init__(self) -> None:
        self._connected = True
        self._status = "playing"
        self._track = {
            "title": "Mock Track",
            "artist": "Mock Artist",
            "album": "Mock Album",
        }
        logger.info("MockBluetoothController ativo (modo desenvolvimento).")

    @property
    def connected(self) -> bool:
        return self._connected

    def play(self) -> bool:
        self._status = "playing"
        logger.info("[MOCK] Bluetooth: Play")
        return True

    def pause(self) -> bool:
        self._status = "paused"
        logger.info("[MOCK] Bluetooth: Pause")
        return True

    def next_track(self) -> bool:
        logger.info("[MOCK] Bluetooth: Next Track")
        return True

    def previous_track(self) -> bool:
        logger.info("[MOCK] Bluetooth: Previous Track")
        return True

    def get_track_info(self) -> dict:
        return self._track

    def get_status(self) -> str:
        return self._status


def create_controller() -> BluetoothMusicController | MockBluetoothController:
    """
    Factory: retorna BluetoothMusicController em Linux, MockBluetoothController em outros sistemas.
    """
    if _is_linux():
        return BluetoothMusicController()
    return MockBluetoothController()
