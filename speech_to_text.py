import os
import speech_recognition as sr

def transcribe_audio(input_wav, output_txt):
    recognizer = sr.Recognizer()

    try:
        with sr.AudioFile(input_wav) as source:
            recognizer.adjust_for_ambient_noise(source)
            audio_data = recognizer.record(source)
            # Transcrição usando o PocketSphinx com o reconhecimento padrão
            text = recognizer.recognize_sphinx(audio_data)
    except FileNotFoundError:
        print(f"Arquivo {input_wav} não encontrado.")
        return
    except sr.UnknownValueError:
        print("Não foi possível entender o áudio.")
        return
    except sr.RequestError as e:
        print(f"Erro ao tentar se conectar ao serviço de reconhecimento: {e}")
        return

    with open(output_txt, 'w') as file:
        file.write(text)

    print(f"Transcrição concluída e salva em {output_txt}")

if __name__ == "__main__":
    input_wav = 'input.wav'
    output_txt = 'input.txt'

    if os.path.exists(output_txt):
        os.remove(output_txt)

    transcribe_audio(input_wav, output_txt)
