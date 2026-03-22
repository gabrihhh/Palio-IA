import pyaudio
import vosk
import json
import logging
import os
import numpy as np
from scipy.signal import resample
import unicodedata
from typing import Callable

logger = logging.getLogger(__name__)

# Wake word padrão — pode ser sobrescrita em iniciar_loop_stt()
_DEFAULT_WAKE_WORD = "carro"


def remove_acentos(texto: str) -> str:
    """Remove os acentos de uma string."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    )


def verificar_palavra(frase: str, palavra: str) -> bool:
    """Verifica se uma palavra está na frase, ignorando acentos e maiúsculas."""
    frase_normalizada = remove_acentos(frase).lower()
    palavra_normalizada = remove_acentos(palavra).lower()
    return palavra_normalizada in frase_normalizada


def resample_audio(audio_data: np.ndarray, original_rate: int, target_rate: int) -> np.ndarray:
    """Reamostra o áudio para a taxa desejada."""
    if original_rate != target_rate:
        num_samples = int(len(audio_data) * target_rate / original_rate)
        return np.asarray(resample(audio_data, num_samples))
    return audio_data


def carregar_modelo(model_path: str) -> vosk.Model:
    """Carrega o modelo Vosk. Encerra o processo se o caminho não existir."""
    if not os.path.exists(model_path):
        logger.error("Modelo Vosk não encontrado em '%s'.", model_path)
        raise SystemExit(1)
    model = vosk.Model(model_path, {"beam": 15, "max-active": 10000})
    logger.info("Modelo Vosk carregado com sucesso.")
    return model


def get_best_microphone(p: pyaudio.PyAudio, target_rate: int) -> tuple[int, int]:
    """Encontra o microfone com a taxa de amostragem mais próxima do target_rate."""
    best_device_index = None

    for i in range(p.get_device_count()):
        device_info = p.get_device_info_by_index(i)
        if int(device_info['maxInputChannels']) > 0:
            rate = int(device_info.get('defaultSampleRate', 0))
            logger.debug("Dispositivo %d: %s, Taxa: %d Hz", i, device_info['name'], rate)
            if best_device_index is None or abs(rate - target_rate) < abs(
                    int(p.get_device_info_by_index(best_device_index)['defaultSampleRate']) - target_rate):
                best_device_index = i

    if best_device_index is None:
        logger.error("Nenhum microfone encontrado.")
        raise SystemExit(1)

    device_info = p.get_device_info_by_index(best_device_index)
    logger.info(
        "Microfone selecionado: %s (%d Hz)",
        device_info['name'],
        int(device_info['defaultSampleRate']),
    )
    return best_device_index, int(device_info['defaultSampleRate'])


def iniciar_loop_stt(
    on_comando: Callable[[str], None],
    wake_word: str = _DEFAULT_WAKE_WORD,
    model_path: str = "model-ptbr",
) -> None:
    """
    Inicia o loop de captura de áudio e reconhecimento de fala.

    Chama on_comando(texto) sempre que a wake_word é detectada no texto reconhecido.
    O texto completo (incluindo a wake word) é passado ao callback.

    Args:
        on_comando:  Callback chamado quando a wake word é detectada.
        wake_word:   Palavra que ativa o assistente (padrão: "carro").
        model_path:  Caminho para o modelo Vosk PT-BR.
    """
    TARGET_RATE = 16000
    CHUNK = 4096

    model = carregar_modelo(model_path)
    p = pyaudio.PyAudio()

    try:
        device_index, device_rate = get_best_microphone(p, TARGET_RATE)

        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=device_rate,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=CHUNK,
        )
    except Exception as e:
        logger.error("Erro ao abrir dispositivo de áudio: %s", e)
        p.terminate()
        raise SystemExit(1)

    recognizer = vosk.KaldiRecognizer(model, TARGET_RATE)
    logger.info("Aguardando wake word '%s'...", wake_word)

    try:
        while True:
            data = stream.read(CHUNK, exception_on_overflow=False)
            if len(data) == 0:
                continue

            audio_data = np.frombuffer(data, dtype=np.int16)
            audio_data = resample_audio(audio_data, device_rate, TARGET_RATE)

            if recognizer.AcceptWaveform(audio_data.tobytes()):
                result = json.loads(recognizer.Result())
                recognized_text = result.get('text', '').strip()

                if not recognized_text:
                    continue

                logger.debug("STT reconheceu: '%s'", recognized_text)

                if verificar_palavra(recognized_text, wake_word):
                    logger.info("Wake word detectada: '%s'", recognized_text)
                    on_comando(recognized_text)
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()


# --- Modo standalone (legado / teste) ---

def _processar_comando_standalone(texto: str) -> None:
    """Handler de teste para rodar speech_to_text.py diretamente."""
    if verificar_palavra(texto, 'próxima'):
        print("Passando a música...")
    elif verificar_palavra(texto, 'voltar'):
        print("Voltando a música...")
    else:
        print(f"Comando recebido: '{texto}'")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    iniciar_loop_stt(on_comando=_processar_comando_standalone)
