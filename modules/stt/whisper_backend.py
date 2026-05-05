"""
modules/stt/whisper_backend.py — Backend STT usando faster-whisper.

Ativado via: python main.py

Arquitetura dois estágios:
  Estágio 1 — sempre ouvindo:
    VAD por energia (com filtro passa-banda para ignorar música) procura pela wake word.
    Ao detectar: chama on_wake_word_cb() → aguarda DUCK_WAIT → entra no estágio 2.

  Estágio 2 — ouvindo comando:
    Captura o próximo utterance completo e chama on_comando(texto).
    Timeout de COMMAND_TIMEOUT segundos → chama on_timeout_cb() e volta ao estágio 1.

Nota: o filtro passa-banda é aplicado apenas para cálculo de energia (VAD).
O áudio enviado ao Whisper é o raw resampled (Whisper performa melhor sem bandpass).
"""

import logging
import os
import time
from typing import Callable, Optional

import numpy as np
import pyaudio

from speech_to_text import get_best_microphone, resample_audio, verificar_palavra, bandpass_filter, pre_emphasis_filter

logger = logging.getLogger(__name__)

_SILENCE_THRESHOLD = int(os.environ.get("WHISPER_SILENCE_THRESHOLD", "400"))
_SILENCE_DURATION = float(os.environ.get("WHISPER_SILENCE_DURATION", "0.8"))
_PRE_SPEECH_SECS = 0.3
_DUCK_WAIT = 0.4
_COMMAND_TIMEOUT = 5.0

# Prompt de contexto injetado em toda transcrição Whisper.
# Envieса o modelo para o vocabulário real do sistema, reduzindo erros fonéticos
# (ex: "carro" → "karo", "mão" → "são").
_INITIAL_PROMPT = (
    "Comandos do carro: carro, próxima, música anterior, pausa, para, toca, play, "
    "aumenta o volume, diminui o volume, conectar, modo de pareamento."
)


def _reset_vad():
    return [], [], False, 0


def iniciar_loop_stt(
    on_comando: Callable[[str], None],
    on_wake_word_cb: Optional[Callable[[], None]] = None,
    on_timeout_cb: Optional[Callable[[], None]] = None,
    wake_word: str = "carro",
    debug: bool = False,
) -> None:
    """
    Inicia o loop STT usando faster-whisper com VAD por energia e dois estágios.

    Args:
        on_comando:       Chamado com o texto do comando (sem wake word).
        on_wake_word_cb:  Chamado imediatamente ao detectar wake word (ex: duck volume).
        on_timeout_cb:    Chamado se estágio 2 expirar sem fala (ex: restaurar volume).
        wake_word:        Palavra de ativação (padrão: "carro").
        debug:            Se True, imprime reconhecimentos em tempo real.
    """
    from faster_whisper import WhisperModel

    SAMPLE_RATE = 16000
    CHUNK = 1024
    PREFERRED_RATE = 48000

    whisper_model_size = os.environ.get("WHISPER_MODEL", "small")
    logger.info("Carregando Whisper '%s' (cpu, int8)...", whisper_model_size)
    model = WhisperModel(whisper_model_size, device="cpu", compute_type="int8")
    logger.info("Modelo Whisper carregado.")

    p = pyaudio.PyAudio()

    try:
        device_index, device_rate = get_best_microphone(p, SAMPLE_RATE)

        capture_rate = device_rate
        try:
            p.is_format_supported(
                PREFERRED_RATE, input_device=device_index,
                input_channels=1, input_format=pyaudio.paInt16
            )
            capture_rate = PREFERRED_RATE
            logger.info("Capturando a %dHz.", capture_rate)
        except Exception:
            logger.info("Capturando a %dHz.", capture_rate)

        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=capture_rate,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=CHUNK,
        )
    except Exception as e:
        logger.error("Erro ao abrir dispositivo de áudio: %s", e)
        p.terminate()
        raise SystemExit(1)

    silence_limit = int(_SILENCE_DURATION * capture_rate / CHUNK)
    pre_buffer_size = int(_PRE_SPEECH_SECS * capture_rate / CHUNK)

    speech_buffer, pre_buffer, in_speech, silence_chunks = _reset_vad()
    stage = 1
    stage2_start = 0.0

    logger.info("Aguardando wake word '%s' (Whisper)...", wake_word)

    try:
        while True:
            data = stream.read(CHUNK, exception_on_overflow=False)
            chunk = np.frombuffer(data, dtype=np.int16)

            # Bandpass apenas para cálculo de energia — não aplica no áudio do Whisper
            chunk_16k = resample_audio(chunk, capture_rate, SAMPLE_RATE)
            chunk_filtered = bandpass_filter(chunk_16k, SAMPLE_RATE)
            vol = int(np.abs(chunk_filtered).mean())

            # Timeout do estágio 2
            if stage == 2 and (time.time() - stage2_start) > _COMMAND_TIMEOUT:
                logger.info("Timeout: nenhum comando detectado em %.0fs.", _COMMAND_TIMEOUT)
                if debug:
                    print("[TIMEOUT] Voltando a ouvir wake word.", flush=True)
                if on_timeout_cb:
                    on_timeout_cb()
                stage = 1
                speech_buffer, pre_buffer, in_speech, silence_chunks = _reset_vad()
                continue

            if vol > _SILENCE_THRESHOLD:
                if not in_speech:
                    in_speech = True
                    speech_buffer = list(pre_buffer)
                silence_chunks = 0
                speech_buffer.append(chunk)
            else:
                if in_speech:
                    silence_chunks += 1
                    speech_buffer.append(chunk)

                    if silence_chunks >= silence_limit:
                        # Transcreve utterance completo
                        audio = np.concatenate(speech_buffer)
                        audio_16k = resample_audio(audio, capture_rate, SAMPLE_RATE)
                        audio_float = audio_16k.astype(np.float32) / 32768.0

                        # Pré-ênfase: realça consoantes e fricativas antes do Whisper
                        audio_float = pre_emphasis_filter(audio_float)

                        segments, _ = model.transcribe(
                            audio_float,
                            language="pt",
                            beam_size=5,
                            initial_prompt=_INITIAL_PROMPT,
                        )
                        text = " ".join(s.text for s in segments).strip()

                        if text:
                            if stage == 1:
                                if debug:
                                    print(f"[STT] {text}", flush=True)
                                else:
                                    logger.debug("Whisper reconheceu: '%s'", text)

                                if verificar_palavra(text, wake_word):
                                    logger.info("Wake word detectada: '%s'", text)
                                    if on_wake_word_cb:
                                        on_wake_word_cb()
                                    time.sleep(_DUCK_WAIT)
                                    stage = 2
                                    stage2_start = time.time()
                                    logger.info("Aguardando comando...")

                            elif stage == 2:
                                if debug:
                                    print(f"[CMD] {text}", flush=True)
                                else:
                                    logger.info("Comando: '%s'", text)
                                on_comando(text)
                                stage = 1

                        speech_buffer, pre_buffer, in_speech, silence_chunks = _reset_vad()
                        continue

                pre_buffer.append(chunk)
                if len(pre_buffer) > pre_buffer_size:
                    pre_buffer.pop(0)
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()
