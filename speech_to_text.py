import pyaudio
import vosk
import json
import os
import numpy as np
from scipy.signal import resample
import unicodedata

def remove_acentos(texto):
    """Remove os acentos de uma string"""
    return ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    )

def verificar_palavra(frase, palavra):
    """Verifica se uma palavra está em qualquer lugar da frase, ignorando acentos e maiúsculas"""
    frase_normalizada = remove_acentos(frase).lower()
    palavra_normalizada = remove_acentos(palavra).lower()
    
    return palavra_normalizada in frase_normalizada


# Caminho do modelo
MODEL_PATH = "model-ptbr"

if not os.path.exists(MODEL_PATH):
    print("O caminho do modelo não foi encontrado.")
    exit(1)

# Carrega o modelo com parâmetros ajustados
model = vosk.Model(MODEL_PATH, {"beam": 15, "max-active": 10000})
print("Modelo carregado com sucesso!")

# Configurações de áudio
TARGET_RATE = 16000
CHUNK = 4096

# Inicializa PyAudio
p = pyaudio.PyAudio()

def get_best_microphone(p, target_rate):
    """Encontra o microfone com a taxa de amostragem mais próxima do TARGET_RATE."""
    best_device_index = None

    for i in range(p.get_device_count()):
        device_info = p.get_device_info_by_index(i)
        if device_info['maxInputChannels'] > 0:  # Verifica se é um dispositivo de entrada
            rate = int(device_info.get('defaultSampleRate', 0))
            print(f"Dispositivo {i}: {device_info['name']}, Taxa máxima: {rate} Hz")
            if best_device_index is None or abs(rate - target_rate) < abs(
                    p.get_device_info_by_index(best_device_index)['defaultSampleRate'] - target_rate):
                best_device_index = i

    if best_device_index is not None:
        device_info = p.get_device_info_by_index(best_device_index)
        print(f"Microfone selecionado: {device_info['name']} com taxa de {device_info['defaultSampleRate']} Hz")
        return best_device_index, int(device_info['defaultSampleRate'])

    print("Nenhum microfone foi encontrado.")
    exit(1)

# Obtém o melhor microfone e sua taxa de amostragem
DEVICE_INDEX, DEVICE_RATE = get_best_microphone(p, TARGET_RATE)

# Inicializa o stream com a taxa de amostragem nativa do microfone
try:
    stream = p.open(format=pyaudio.paInt16,
                    channels=1,
                    rate=DEVICE_RATE,
                    input=True,
                    input_device_index=DEVICE_INDEX,
                    frames_per_buffer=CHUNK)
except Exception as e:
    print(f"Erro ao abrir o dispositivo de áudio: {e}")
    exit(1)

# Reamostrar para o TARGET_RATE, se necessário
def resample_audio(audio_data, original_rate, target_rate):
    """Reamostra o áudio para a taxa desejada."""
    if original_rate != target_rate:
        num_samples = int(len(audio_data) * target_rate / original_rate)
        return resample(audio_data, num_samples)
    return audio_data

recognizer = vosk.KaldiRecognizer(model, TARGET_RATE)

print("Aguardando o comando...")

# Loop principal
while True:
    data = stream.read(CHUNK, exception_on_overflow=False)
    if len(data) == 0:
        print("Nenhum áudio capturado.")
        continue

    # Converte o áudio para numpy e reamostra se necessário
    audio_data = np.frombuffer(data, dtype=np.int16)
    audio_data = resample_audio(audio_data, DEVICE_RATE, TARGET_RATE)

    # Processa o áudio com o modelo
    if recognizer.AcceptWaveform(audio_data.tobytes()):
        result = json.loads(recognizer.Result())
        recognized_text = result.get('text', '').strip()

        print("DEBUG: Resultados do modelo:", result)

        # Verifica se a palavra "carro" está na frase
        if "carro" in recognized_text:
            print(f"Comando detectado: '{recognized_text}'")

            # Verifica se o comando "proxima" ou "voltar" está presente na mesma frase
            if verificar_palavra(recognized_text, 'próxima'):
                print("Passando a música...")
            elif verificar_palavra(recognized_text, 'voltar'):
                print("Voltando a música...")
            else:
                print(f"Comando desconhecido na frase: '{recognized_text}'")
