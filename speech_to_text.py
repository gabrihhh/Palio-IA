import pyaudio
import vosk
import json
import logging
import os
import time
import numpy as np
from difflib import SequenceMatcher
from scipy.signal import resample_poly, butter, sosfilt
import unicodedata
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Wake word padrão — pode ser sobrescrita em iniciar_loop_stt()
_DEFAULT_WAKE_WORD = "carro"


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


def bandpass_filter(audio: np.ndarray, sample_rate: int, low_hz: int = 300, high_hz: int = 3400) -> np.ndarray:
    """Filtra o áudio para a faixa de voz humana (300–3400Hz).

    Reduz bleeding de música (graves e agudos fora da faixa de fala).
    Aplicado antes do STT para melhorar VAD e reconhecimento.
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


def carregar_modelo(model_path: str) -> vosk.Model:
    """Carrega o modelo Vosk. Encerra o processo se o caminho não existir."""
    if not os.path.exists(model_path):
        logger.error("Modelo Vosk não encontrado em '%s'.", model_path)
        raise SystemExit(1)
    model = vosk.Model(model_path)
    logger.info("Modelo Vosk carregado com sucesso.")
    return model


def get_best_microphone(p: pyaudio.PyAudio, target_rate: int) -> tuple[int, int]:
    """Encontra o microfone com a taxa de amostragem mais próxima do target_rate.

    Se a variável de ambiente AUDIO_DEVICE estiver definida, usa o índice especificado.
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
    on_wake_word_cb: Optional[Callable[[], None]] = None,
    on_timeout_cb: Optional[Callable[[], None]] = None,
    wake_word: str = _DEFAULT_WAKE_WORD,
    model_path: str = "model-ptbr",
    debug: bool = False,
) -> None:
    """
    Inicia o loop de captura de áudio com arquitetura dois estágios.

    Estágio 1 — sempre ouvindo:
      Aplica filtro passa-banda + VAD e procura apenas pela wake word.
      Ao detectar: chama on_wake_word_cb(), aguarda 400ms (duck settle), entra no estágio 2.

    Estágio 2 — ouvindo comando:
      Captura o próximo utterance e chama on_comando(texto).
      Timeout de 5s sem fala → chama on_timeout_cb() e volta ao estágio 1.

    Args:
        on_comando:       Callback chamado com o texto do comando (sem wake word).
        on_wake_word_cb:  Chamado imediatamente ao detectar a wake word (ex: duck volume).
        on_timeout_cb:    Chamado se estágio 2 expirar sem comando (ex: restaurar volume).
        wake_word:        Palavra de ativação (padrão: "carro").
        model_path:       Caminho para o modelo Vosk PT-BR.
        debug:            Se True, imprime reconhecimentos em tempo real.
    """
    TARGET_RATE = 16000
    CHUNK = 4096
    PREFERRED_RATE = 48000  # ratio 3:1 com 16kHz — resampling limpo
    DUCK_WAIT = 0.4         # segundos para o duck efetivar antes de ouvir o comando
    COMMAND_TIMEOUT = 5.0   # segundos máx aguardando comando no estágio 2

    model = carregar_modelo(model_path)
    p = pyaudio.PyAudio()

    try:
        device_index, device_rate = get_best_microphone(p, TARGET_RATE)

        # Tenta capturar a 48kHz (ratio 3:1 com 16kHz) para resampling mais limpo
        capture_rate = device_rate
        try:
            p.is_format_supported(
                PREFERRED_RATE, input_device=device_index,
                input_channels=1, input_format=pyaudio.paInt16
            )
            capture_rate = PREFERRED_RATE
            logger.info("Capturando a %dHz (ratio limpo 3:1 com 16kHz).", capture_rate)
        except Exception:
            logger.info("Capturando a %dHz (taxa padrão do dispositivo).", capture_rate)

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

    recognizer = vosk.KaldiRecognizer(model, TARGET_RATE)
    logger.info("Aguardando wake word '%s'...", wake_word)

    stage = 1           # 1 = esperando wake word | 2 = esperando comando
    stage2_start = 0.0

    try:
        while True:
            data = stream.read(CHUNK, exception_on_overflow=False)
            if len(data) == 0:
                continue

            raw = np.frombuffer(data, dtype=np.int16)
            audio_data = resample_audio(raw, capture_rate, TARGET_RATE)
            audio_data = bandpass_filter(audio_data, TARGET_RATE)

            # Timeout do estágio 2
            if stage == 2 and (time.time() - stage2_start) > COMMAND_TIMEOUT:
                logger.info("Timeout: nenhum comando detectado em %.0fs.", COMMAND_TIMEOUT)
                if debug:
                    print("[TIMEOUT] Voltando a ouvir wake word.", flush=True)
                if on_timeout_cb:
                    on_timeout_cb()
                stage = 1
                recognizer = vosk.KaldiRecognizer(model, TARGET_RATE)

            if recognizer.AcceptWaveform(audio_data.tobytes()):
                result = json.loads(recognizer.Result())
                recognized_text = result.get('text', '').strip()

                if not recognized_text:
                    continue

                if stage == 1:
                    if debug:
                        print(f"[STT] {recognized_text}", flush=True)
                    else:
                        logger.debug("STT reconheceu: '%s'", recognized_text)

                    if verificar_palavra(recognized_text, wake_word):
                        logger.info("Wake word detectada: '%s'", recognized_text)
                        if on_wake_word_cb:
                            on_wake_word_cb()
                        time.sleep(DUCK_WAIT)
                        recognizer = vosk.KaldiRecognizer(model, TARGET_RATE)
                        stage = 2
                        stage2_start = time.time()
                        logger.info("Aguardando comando...")

                elif stage == 2:
                    if debug:
                        print(f"[CMD] {recognized_text}", flush=True)
                    else:
                        logger.info("Comando: '%s'", recognized_text)
                    on_comando(recognized_text)
                    stage = 1
                    recognizer = vosk.KaldiRecognizer(model, TARGET_RATE)

            elif debug and stage == 1:
                partial = json.loads(recognizer.PartialResult()).get('partial', '')
                vol = int(np.abs(raw).mean())
                if partial:
                    print(f"[VOL:{vol:4d}] {partial}", flush=True)
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
