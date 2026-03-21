"""
modules/core/dispatcher.py

Roteador de intenção (intent dispatcher).

Recebe o texto reconhecido pelo STT (já filtrado pela wake word) e decide:
  1. Modo pareamento ativo? → delega ao PairingManager
  2. É um comando de pareamento/dispositivos? → ativa PairingManager ou executa ação
  3. É um comando de música mapeado? → executa via BluetoothMusicController
  4. Nenhum dos anteriores? → envia ao OllamaClient para resposta livre

A saída de qualquer caminho é sempre uma string de texto que será lida pelo TTS.

Comandos de música reconhecidos (insensíveis a acentos e maiúsculas):
  - "próxima" / "proxima" / "passa" / "passa música" → next_track()
  - "volta" / "voltar" / "anterior" / "volta música"  → previous_track()
  - "pausa" / "pausar" / "para" / "para música"       → pause()
  - "toca" / "tocar" / "play" / "continua" / "resume" → play()
  - "que música é essa" / "qual é a música"           → get_track_info()

Comandos de pareamento (manual — scan ao vivo):
  - "modo parear" / "parear" / "pareamento"           → inicia fluxo de scan + pair

Comandos de pareamento automático (usa os salvos):
  - "pareamento automático" / "conectar automatico"   → conecta o último sink + source salvos

Comandos de gerenciamento de dispositivos:
  - "quais dispositivos" / "lista dispositivos"       → lista dispositivos salvos
  - "remover <nome>" / "desparear <nome>"             → remove dispositivo
  - "reconectar" / "conectar dispositivos"            → reconecta todos os dispositivos salvos
"""

import logging
import unicodedata
from typing import Callable

from modules.bluetooth.audio import VolumeController, MockVolumeController
from modules.bluetooth.music import BluetoothMusicController, MockBluetoothController
from modules.bluetooth.pairing import PairingManager, create_pairing_manager
from modules.llm.client import OllamaClient

logger = logging.getLogger(__name__)

# Tipos unificados
AnyController = BluetoothMusicController | MockBluetoothController
AnyVolumeController = VolumeController | MockVolumeController

# Mapa Vosk PT-BR: palavras → dígito (1-10)
_PT_NUMEROS: dict[str, int] = {
    "um": 1, "uma": 1,
    "dois": 2, "duas": 2,
    "tres": 3,
    "quatro": 4,
    "cinco": 5,
    "seis": 6,
    "sete": 7,
    "oito": 8,
    "nove": 9,
    "dez": 10,
    # fallback numérico (caso o Vosk reconheça dígito)
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5,
    "6": 6, "7": 7, "8": 8, "9": 9, "10": 10,
}


def _normalizar(texto: str) -> str:
    """Remove acentos e converte para minúsculas."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    ).lower()


# ---------------------------------------------------------------------------
# Intenções de música
# ---------------------------------------------------------------------------

_MUSIC_INTENTS: list[tuple[list[str], str]] = [
    (["proxima", "passa", "passa musica", "skip", "pula"], "next"),
    (["volta", "voltar", "anterior", "musica anterior", "volta musica"], "previous"),
    (["pausa", "pausar", "para musica", "stop"], "pause"),
    (["toca", "tocar", "play", "continua", "resume", "continuar"], "play"),
    (["que musica e essa", "qual e a musica", "qual musica", "o que ta tocando",
      "nome da musica", "nome da faixa"], "track_info"),
]


# ---------------------------------------------------------------------------
# Intenções de volume
# ---------------------------------------------------------------------------

_VOLUME_UP_TRIGGERS = ["aumenta", "aumentar", "sobe", "mais volume", "aumenta o volume", "aumentar volume"]
_VOLUME_DOWN_TRIGGERS = ["diminui", "diminuir", "desce", "menos volume", "diminui o volume", "abaixa", "abaixar"]


def _detectar_intencao_volume(texto_norm: str) -> tuple[str, int] | None:
    """
    Detecta intenção de controle de volume.

    Retorna:
        ("up",   0)       para "aumenta"
        ("down", 0)       para "diminui"
        ("set",  step)    para "volume cinco" (step 1-10)
        ("set",  -1)      para "volume" sem número reconhecível
        None              se não for comando de volume
    """
    for t in _VOLUME_UP_TRIGGERS:
        if t in texto_norm:
            return ("up", 0)

    for t in _VOLUME_DOWN_TRIGGERS:
        if t in texto_norm:
            return ("down", 0)

    if "volume" in texto_norm:
        tokens = texto_norm.split()
        for i, tok in enumerate(tokens):
            if tok == "volume" and i + 1 < len(tokens):
                step = _PT_NUMEROS.get(tokens[i + 1])
                if step is not None:
                    return ("set", step)
        return ("set", -1)  # "volume" detectado mas sem número

    return None


def _detectar_intencao_musica(texto: str) -> str | None:
    texto_norm = _normalizar(texto)
    for palavras, intencao in _MUSIC_INTENTS:
        for palavra in palavras:
            if palavra in texto_norm:
                return intencao
    return None


# ---------------------------------------------------------------------------
# Intenções de pareamento
# ---------------------------------------------------------------------------

_PAIRING_TRIGGERS = [
    "modo parear", "modo pareamento", "parear dispositivo",
    "pareie", "adicionar dispositivo", "novo dispositivo",
]

# Triggers para pareamento automático — verificados ANTES dos triggers manuais
# para "pareamento automatico" não cair em "pareamento" acima
_AUTO_PAIRING_TRIGGERS = [
    "pareamento automatico", "parear automatico", "conectar automatico",
    "conexao automatica", "conectar os salvos", "conectar salvos",
]

_DEVICE_LIST_TRIGGERS = [
    "quais dispositivos", "lista de dispositivos", "dispositivos pareados",
    "que dispositivos", "meus dispositivos",
]

_DEVICE_REMOVE_TRIGGERS = [
    "remover ", "desparear ", "excluir dispositivo ", "deletar dispositivo ",
]

_RECONNECT_TRIGGERS = [
    "reconectar", "reconecta", "conectar dispositivos", "reconectar dispositivos",
    "conecta o bluetooth",
]


def _detectar_intencao_pareamento(texto_norm: str) -> str | None:
    """Retorna a intenção de gerenciamento de dispositivos ou None."""
    # Automático primeiro (evita match parcial com triggers manuais)
    for t in _AUTO_PAIRING_TRIGGERS:
        if t in texto_norm:
            return "pareamento_automatico"

    for t in _PAIRING_TRIGGERS:
        if t in texto_norm:
            return "iniciar_pareamento"

    for t in _DEVICE_LIST_TRIGGERS:
        if t in texto_norm:
            return "listar"

    for t in _DEVICE_REMOVE_TRIGGERS:
        if t in texto_norm:
            return "remover"

    for t in _RECONNECT_TRIGGERS:
        if t in texto_norm:
            return "reconectar"

    return None


def _extrair_nome_remocao(texto_norm: str) -> str:
    """Extrai o nome do dispositivo a remover do comando de voz."""
    for trigger in _DEVICE_REMOVE_TRIGGERS:
        if trigger in texto_norm:
            return texto_norm.split(trigger, 1)[1].strip()
    return ""


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

class Dispatcher:
    """
    Roteador central do sistema Palio-IA.

    Recebe texto do STT e retorna a resposta textual para o TTS.
    """

    def __init__(
        self,
        bluetooth: AnyController,
        llm: OllamaClient,
        falar_cb: Callable[[str], None],
        volume: AnyVolumeController | None = None,
    ) -> None:
        self._bt = bluetooth
        self._llm = llm
        self._volume = volume
        self._pairing: PairingManager = create_pairing_manager(falar_cb)

    def processar(self, texto: str) -> str:
        """
        Processa o texto reconhecido e retorna a resposta textual.

        Args:
            texto: Texto reconhecido pelo STT (já sem a wake word).

        Returns:
            String com a resposta a ser lida pelo TTS.
            Pode retornar string vazia quando o PairingManager já
            chamou falar_cb diretamente (ex: durante o scan).
        """
        logger.info("Dispatcher recebeu: '%s'", texto)
        texto_norm = _normalizar(texto)

        # --- Modo pareamento ativo: redireciona tudo para o PairingManager ---
        if self._pairing.ativo:
            return self._pairing.processar(texto)

        # --- Comandos de gerenciamento de dispositivos ---
        intencao_pair = _detectar_intencao_pareamento(texto_norm)
        if intencao_pair is not None:
            return self._executar_pareamento(intencao_pair, texto_norm)

        # --- Comandos de volume ---
        intencao_volume = _detectar_intencao_volume(texto_norm)
        if intencao_volume is not None:
            return self._executar_volume(intencao_volume)

        # --- Comandos de música ---
        intencao_musica = _detectar_intencao_musica(texto)
        if intencao_musica is not None:
            return self._executar_musica(intencao_musica)

        # --- LLM ---
        return self._llm.chat(texto)

    # ------------------------------------------------------------------
    # Execução de pareamento
    # ------------------------------------------------------------------

    def _executar_pareamento(self, intencao: str, texto_norm: str) -> str:
        if intencao == "iniciar_pareamento":
            return self._pairing.iniciar_modo_parear()

        if intencao == "pareamento_automatico":
            return self._pairing.pareamento_automatico()

        if intencao == "listar":
            devices = self._pairing.listar_dispositivos()
            if not devices:
                return "Não tem nenhum dispositivo pareado ainda."
            partes = [f"{d.apelido} como {d.role_label()}" for d in devices]
            if len(partes) == 1:
                return f"Tenho um dispositivo: {partes[0]}."
            return "Tenho " + ", ".join(partes[:-1]) + f" e {partes[-1]}."

        if intencao == "remover":
            nome = _extrair_nome_remocao(texto_norm)
            if not nome:
                return "Qual dispositivo você quer remover?"
            return self._pairing.remover_dispositivo(nome)

        if intencao == "reconectar":
            return self._pairing.reconectar_todos()

        return "Não entendi o comando de dispositivo."

    # ------------------------------------------------------------------
    # Execução de música
    # ------------------------------------------------------------------

    def _executar_musica(self, intencao: str) -> str:
        if not self._bt.connected:
            return "Não tem nenhum celular conectado aqui não."

        if intencao == "next":
            ok = self._bt.next_track()
            return "Vou passar pra próxima." if ok else "Não consegui passar a música."

        if intencao == "previous":
            ok = self._bt.previous_track()
            return "Voltei pra anterior." if ok else "Não consegui voltar a música."

        if intencao == "pause":
            ok = self._bt.pause()
            return "Pausei aqui." if ok else "Não consegui pausar."

        if intencao == "play":
            ok = self._bt.play()
            return "Continuando." if ok else "Não consegui retomar."

        if intencao == "track_info":
            info = self._bt.get_track_info()
            if info.get("title"):
                artista = f" do {info['artist']}" if info.get("artist") else ""
                return f"Tá tocando {info['title']}{artista}."
            return "Não tô conseguindo ver o nome da música."

        return "Não entendi o que você quis."

    # ------------------------------------------------------------------
    # Execução de volume
    # ------------------------------------------------------------------

    def _executar_volume(self, intencao: tuple[str, int]) -> str:
        if self._volume is None:
            return "Controle de volume não está disponível."

        acao, step = intencao

        if acao == "up":
            novo = self._volume.aumentar()
            if novo < 0:
                return "Não consegui aumentar o volume."
            return f"Volume no {novo // 10}."

        if acao == "down":
            novo = self._volume.diminuir()
            if novo < 0:
                return "Não consegui diminuir o volume."
            return f"Volume no {novo // 10}."

        if acao == "set":
            if step == -1:
                return ""
            ok = self._volume.set_step(step)
            if not ok:
                return "Não consegui definir o volume."
            return f"Volume no {step}."

        return "Não entendi o comando de volume."
