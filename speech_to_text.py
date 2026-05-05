"""
speech_to_text.py

Utilitários de áudio compartilhados pelo backend Whisper.

  - remove_acentos / verificar_palavra  — normalização e fuzzy match para wake word
  - pre_emphasis_filter                 — realça consoantes antes da transcrição
  - bandpass_filter                     — filtra faixa de voz humana (VAD)
  - resample_audio                      — 48kHz → 16kHz via resample_poly
  - get_best_microphone                 — seleciona mic USB sobre dispositivos virtuais
"""

import pyaudio
import logging
import os
import numpy as np
from difflib import SequenceMatcher
from scipy.signal import resample_poly, butter, sosfilt
import unicodedata

logger = logging.getLogger(__name__)


def remove_acentos(texto: str) -> str:
    """Remove os acentos de uma string."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    )


def _similaridade(a: str, b: str) -> float:
    """Retorna similaridade entre duas strings (0.0 a 1.0)."""
    return SequenceMatcher(None, a, b).ratio()


def verificar_palavra(frase: str, palavra: str, limiar: float = 0.75) -> bool:
    """Verifica se uma palavra está na frase, ignorando acentos e maiúsculas.

    Aceita correspondências fonéticas aproximadas (ex: 'carla' → 'carro')
    usando similaridade de string com threshold configurável.
    """
    frase_normalizada = remove_acentos(frase).lower()
    palavra_normalizada = remove_acentos(palavra).lower()

    # Correspondência exata (substring)
    if palavra_normalizada in frase_normalizada:
        return True

    # Fuzzy: verifica cada palavra da frase individualmente
    for token in frase_normalizada.split():
        if _similaridade(token, palavra_normalizada) >= limiar:
            return True

    return False


def pre_emphasis_filter(audio: np.ndarray, coef: float = 0.97) -> np.ndarray:
    """Realça frequências altas (consoantes, fricativas) para melhorar transcrição STT.

    Amplifica diferenças entre samples adjacentes, tornando fonemas como
    'r', 's', 'c' mais distintos. Aplicar ao áudio float32 antes de enviar ao modelo.
    Coeficiente padrão 0.97 é o valor clássico para pré-ênfase de fala.
    """
    if len(audio) < 2:
        return audio
    emphasized = np.concatenate([[audio[0]], audio[1:] - coef * audio[:-1]])
    return emphasized.astype(audio.dtype)


def bandpass_filter(audio: np.ndarray, sample_rate: int, low_hz: int = 300, high_hz: int = 3400) -> np.ndarray:
    """Filtra o áudio para a faixa de voz humana (300–3400Hz).

    Reduz bleeding de música (graves e agudos fora da faixa de fala).
    Usado para cálculo de energia no VAD — não aplicado ao áudio enviado ao Whisper.
    """
    nyq = sample_rate / 2.0
    sos = butter(4, [low_hz / nyq, high_hz / nyq], btype='band', output='sos')
    filtered = sosfilt(sos, audio.astype(np.float32))
    return np.clip(filtered, -32768, 32767).astype(np.int16)


def resample_audio(audio_data: np.ndarray, original_rate: int, target_rate: int) -> np.ndarray:
    """Reamostra o áudio para a taxa desejada, mantendo dtype int16."""
    if original_rate != target_rate:
        from math import gcd
        g = gcd(original_rate, target_rate)
        up = target_rate // g
        down = original_rate // g
        resampled = resample_poly(audio_data, up, down)
        return np.clip(resampled, -32768, 32767).astype(np.int16)
    return audio_data


# Nomes de dispositivos virtuais que devem ter menor prioridade que hardware real
_VIRTUAL_DEVICE_NAMES = {"pulse", "pipewire", "default", "sysdefault"}


def get_best_microphone(p: pyaudio.PyAudio, target_rate: int) -> tuple[int, int]:
    """Seleciona o melhor microfone disponível com prioridades:

    1. Se AUDIO_DEVICE estiver definido, usa o índice especificado diretamente.
    2. Descarta dispositivos Monitor (loopback de saída — nunca são microfones).
    3. Prefere hardware real sobre dispositivos virtuais (pulse, pipewire, default).
    4. Dentro de cada grupo, escolhe pelo defaultSampleRate mais próximo de target_rate.
    5. Se só sobrarem virtuais, usa o melhor entre eles.
    """
    env_device = os.environ.get("AUDIO_DEVICE")
    if env_device is not None:
        try:
            device_index = int(env_device)
            device_info = p.get_device_info_by_index(device_index)
            if int(device_info['maxInputChannels']) == 0:
                logger.error("Dispositivo %d (%s) não tem canais de entrada.", device_index, device_info['name'])
                raise SystemExit(1)
            logger.info(
                "Microfone selecionado via AUDIO_DEVICE=%d: %s (%d Hz)",
                device_index,
                device_info['name'],
                int(device_info['defaultSampleRate']),
            )
            return device_index, int(device_info['defaultSampleRate'])
        except (ValueError, OSError) as e:
            logger.error("AUDIO_DEVICE inválido: %s", e)
            raise SystemExit(1)

    hardware: list[tuple[int, int, str]] = []   # (index, rate, name)
    virtual: list[tuple[int, int, str]] = []

    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if int(info['maxInputChannels']) == 0:
            continue
        name = info['name']
        rate = int(info.get('defaultSampleRate', 0))
        name_lower = name.lower()

        # Monitor = loopback de saída de áudio, nunca um microfone
        if 'monitor' in name_lower:
            logger.debug("Ignorando Monitor: %s", name)
            continue

        logger.debug("Candidato %d: %s (%d Hz)", i, name, rate)

        if any(v == name_lower for v in _VIRTUAL_DEVICE_NAMES):
            virtual.append((i, rate, name))
        else:
            hardware.append((i, rate, name))

    pool = hardware if hardware else virtual

    if not pool:
        logger.error("Nenhum microfone encontrado.")
        raise SystemExit(1)

    best_index, best_rate, best_name = min(pool, key=lambda x: abs(x[1] - target_rate))

    if not hardware:
        logger.warning("Nenhum hardware de microfone encontrado; usando dispositivo virtual.")

    logger.info("Microfone selecionado: %s (%d Hz)", best_name, best_rate)
    return best_index, best_rate
