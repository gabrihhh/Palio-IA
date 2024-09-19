import audioread
from pydub import AudioSegment
import speech_recognition as sr
import os

# Caminho para o arquivo MP3
mp3_file_path = 'input.mp3'
wav_file_path = 'audio.wav'

# Converte MP3 para WAV usando pydub
try:
    with audioread.audio_open(mp3_file_path) as audio_file:
        audio = AudioSegment.from_file(mp3_file_path, format='mp3')
        audio.export(wav_file_path, format='wav')
        print(f'{mp3_file_path} convertido para {wav_file_path}.')
except Exception as e:
    print(f"Erro ao converter MP3 para WAV: {e}")
    exit()

# Exclui o arquivo MP3 após a conversão
if os.path.exists(mp3_file_path):
    os.remove(mp3_file_path)
    print(f'{mp3_file_path} foi excluído.')

# Cria um objeto Recognizer
recognizer = sr.Recognizer()

# Carrega o arquivo de áudio WAV
try:
    with sr.AudioFile(wav_file_path) as source:
        # Ajusta o reconhecimento para o nível de ruído
        recognizer.adjust_for_ambient_noise(source)
        # Lê o arquivo de áudio
        audio = recognizer.record(source)
        # Usa o Google Web Speech API para reconhecer o áudio
        text = recognizer.recognize_google(audio, language='pt-BR')
        print("Texto transcrito:", text)
except sr.UnknownValueError:
    print("O Google Web Speech API não conseguiu entender o áudio.")
except sr.RequestError as e:
    print(f"Erro na solicitação ao Google Web Speech API: {e}")
except Exception as e:
    print(f"Erro ao processar o arquivo WAV: {e}")

# Exclui o arquivo WAV após a transcrição
if os.path.exists(wav_file_path):
    os.remove(wav_file_path)
    print(f'{wav_file_path} foi excluído.')
