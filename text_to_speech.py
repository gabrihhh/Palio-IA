import pyttsx3
import os

# Caminho para o arquivo de saída
audio_file = 'output.wav'
file_path = 'output.txt'

# Inicializar o mecanismo TTS
engine = pyttsx3.init()

# Configurar a taxa de fala
engine.setProperty('rate', 200)  # Ajuste a velocidade conforme necessário

# Configurar o volume
engine.setProperty('volume', 1)  # Volume entre 0 e 1

with open(file_path, 'r', encoding='utf-8') as file:
    content = file.read()

# Salvar o áudio em um arquivo WAV
engine.save_to_file(content, audio_file)

# Executar o áudio
engine.runAndWait()

# Reproduzir o áudio
try:
    import winsound
    winsound.PlaySound(audio_file, winsound.SND_FILENAME)
except ImportError:
    print(f"Por favor, instale o módulo 'winsound' para reprodução de áudio no Windows.")
except Exception as e:
    print(f"Ocorreu um erro ao tentar reproduzir o áudio: {e}")

# # Limpar o arquivo de áudio depois de reproduzir
if os.path.exists(audio_file):
    os.remove(audio_file)
