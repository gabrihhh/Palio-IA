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

from modules.bluetooth.music import BluetoothMusicController, MockBluetoothController
from modules.bluetooth.pairing import PairingManager, create_pairing_manager
from modules.llm.client import OllamaClient

logger = logging.getLogger(__name__)

# Tipo unificado para o controller de música
AnyController = BluetoothMusicController | MockBluetoothController


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
    ) -> None:
        self._bt = bluetooth
        self._llm = llm
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
