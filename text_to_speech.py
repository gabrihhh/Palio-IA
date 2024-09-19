from gtts import gTTS
from playsound import playsound

# Ler o conteúdo de um arquivo de texto
file_path = 'fala.txt'

# Abrir o arquivo em modo de leitura
with open(file_path, 'r', encoding='utf-8') as file:
    content = file.read()  # Lê o conteúdo do arquivo


# Configurar a linguagem e gerar o arquivo de áudio
tts = gTTS(text=content, lang='pt-br')

# Salvar o arquivo de áudio
audio_file = "output.mp3"
tts.save("output.mp3")

playsound(audio_file)
