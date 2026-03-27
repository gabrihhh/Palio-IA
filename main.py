"""
main.py — Palio-IA

Orquestrador principal do assistente de voz Palio.

Fluxo:
  1. Inicializa todos os módulos (STT, TTS, Bluetooth, LLM)
  2. Inicia o loop de escuta STT
  3. Ao detectar wake word "palio", extrai o restante do texto
  4. Passa o texto ao Dispatcher (comando de música ou conversa LLM)
  5. Lê a resposta via TTS

Para rodar:
  python main.py

Pré-requisitos:
  - Modelo Vosk PT-BR em ./model-ptbr/
  - Ollama rodando: ollama serve && ollama pull llama3.2:3b  (opcional — TTS funciona sem)
  - Linux + bluez para controle Bluetooth  (opcional — mock usado em outros sistemas)
"""

import logging
import os
import sys
import numpy as np
import pyttsx3
import sounddevice as sd
import soundfile as sf

from speech_to_text import iniciar_loop_stt, verificar_palavra
from modules.bluetooth.audio import create_volume_controller
from modules.bluetooth.music import create_controller
from modules.bluetooth.audio_duck import create_audio_duck
from modules.llm.client import OllamaClient
from modules.core.dispatcher import Dispatcher

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("palio")

# --- Wake word ---
WAKE_WORD = "carro"


# --- Som de boot ---

def tocar_boot() -> None:
    """Toca dois bipes curtos e suaves como sinal de inicialização."""
    sample_rate = 44100
    freq = 880       # Lá5 — tom limpo e discreto
    duration = 0.12  # segundos por bipe
    gap = 0.08       # pausa entre bipes

    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    bipe = (np.sin(2 * np.pi * freq * t) * 0.3).astype(np.float32)
    silencio = np.zeros(int(sample_rate * gap), dtype=np.float32)

    audio = np.concatenate([bipe, silencio, bipe])
    try:
        sd.play(audio, samplerate=sample_rate)
        sd.wait()
    except Exception as e:
        logger.warning("Não foi possível tocar som de boot: %s", e)


# --- TTS ---

def falar(texto: str) -> None:
    """Converte texto em fala e reproduz pelo dispositivo de saída de áudio."""
    logger.info("TTS: '%s'", texto)
    engine = pyttsx3.init()
    engine.setProperty('rate', 160)
    engine.setProperty('volume', 1.0)
    engine.save_to_file(texto, 'output.wav')
    engine.runAndWait()

    try:
        data, samplerate = sf.read('output.wav')
        sd.play(data, samplerate)
        sd.wait()
    except Exception as e:
        logger.error("Erro ao reproduzir TTS: %s", e)
    finally:
        if os.path.exists('output.wav'):
            os.remove('output.wav')


# --- Inicialização ---

def inicializar() -> tuple[Dispatcher, object, object]:
    """Inicializa todos os módulos e retorna o Dispatcher, AudioDuck e VolumeController."""
    logger.info("Inicializando Palio-IA...")

    bt = create_controller()
    if bt.connected:
        logger.info("Bluetooth: controlador conectado.")
    else:
        logger.warning("Bluetooth: não conectado. Comandos de música indisponíveis.")

    llm = OllamaClient(model="llama3.2:3b")
    if llm.available:
        logger.info("LLM: Ollama disponível.")
    else:
        logger.warning("LLM: Ollama indisponível. Respostas livres não funcionarão.")

    duck = create_audio_duck()
    logger.info("AudioDuck inicializado.")

    volume = create_volume_controller()
    logger.info("VolumeController inicializado.")

    dispatcher = Dispatcher(bluetooth=bt, llm=llm, falar_cb=falar, volume=volume)
    return dispatcher, duck, volume


# --- Handler de comandos STT ---

def _extrair_comando_apos_wake_word(texto: str) -> str:
    """
    Remove a wake word do início do texto reconhecido.
    Ex: "palio próxima música" → "próxima música"
    """
    import unicodedata

    def _norm(t: str) -> str:
        return ''.join(
            c for c in unicodedata.normalize('NFD', t) if unicodedata.category(c) != 'Mn'
        ).lower()

    texto_norm = _norm(texto)
    wake_norm = _norm(WAKE_WORD)

    if texto_norm.startswith(wake_norm):
        return texto[len(WAKE_WORD):].strip()
    # Wake word no meio da frase — retorna tudo após ela
    idx = texto_norm.find(wake_norm)
    if idx >= 0:
        return texto[idx + len(WAKE_WORD):].strip()
    return texto.strip()


def criar_handler(dispatcher: Dispatcher, duck, volume):
    """Cria o callback de comando para o loop STT."""

    def on_comando(texto: str) -> None:
        logger.info("Wake word detectada. Texto completo: '%s'", texto)

        # Baixa o volume imediatamente ao detectar a wake word
        duck.on_wake_word()

        try:
            comando = _extrair_comando_apos_wake_word(texto)

            if not comando:
                falar("Oi. Pode falar.")
                return

            resposta = dispatcher.processar(comando)
            # O PairingManager pode chamar falar() diretamente — dispatcher retorna "" nesses casos
            if resposta:
                falar(resposta)
        finally:
            # Restaura o volume original antes de aplicar qualquer mudança pedida
            duck.on_done()

            # Aplica volume pendente APÓS o duck restaurar — evita que o duck sobrescreva
            pending = dispatcher.consume_pending_volume()
            if pending is not None:
                acao, step = pending
                if acao == "up":
                    volume.aumentar()
                elif acao == "down":
                    volume.diminuir()
                elif acao == "set":
                    volume.set_step(step)

    return on_comando


# --- Entry point ---

if __name__ == '__main__':
    debug_mode = '--debug' in sys.argv

    if debug_mode:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.info("Modo debug ativado — exibindo tudo que o Vosk reconhece.")

    dispatcher, duck, volume = inicializar()
    handler = criar_handler(dispatcher, duck, volume)

    tocar_boot()
    logger.info("Loop STT iniciado. Wake word: '%s'", WAKE_WORD)

    try:
        iniciar_loop_stt(on_comando=handler, wake_word=WAKE_WORD, debug=debug_mode)
    except KeyboardInterrupt:
        logger.info("Encerrando Palio-IA.")
        sys.exit(0)
