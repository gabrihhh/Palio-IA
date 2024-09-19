from moviepy.editor import AudioFileClip, concatenate_audioclips
import speech_recognition as sr
import os
from pydub import AudioSegment

# Caminho para o arquivo MP3
mp3_file_path = 'input.mp3'
wav_file_path = 'audio.wav'

#cria arquivo de silencio
silence_duration_ms = 1000
silence = AudioSegment.silent(duration=silence_duration_ms)
silence.export("silence.wav", format="wav")

def convert_mp3_to_wav_with_silence(mp3_file_path, wav_file_path, silence_duration_s=1):
    # Carregar o arquivo MP3
    audio_clip = AudioFileClip(mp3_file_path)
    
    # Criar um clip de silêncio
    silence = AudioFileClip("silence.wav").subclip(0, silence_duration_s)
    
    # Adicionar silêncio no início
    final_clip = concatenate_audioclips([silence, audio_clip])
    
    # Exportar o arquivo como WAV
    final_clip.write_audiofile(wav_file_path, codec='pcm_s16le')


convert_mp3_to_wav_with_silence("input.mp3", "audio.wav")

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
