import speech_recognition as sr

def process_command(command):
    if "ligar luz" in command:
        print("Luz ligada!")
    elif "desligar luz" in command:
        print("Luz desligada!")
    elif "tocar música" in command:
        print("Tocando música!")
    else:
        print("Comando não reconhecido.")

def main():
    recognizer = sr.Recognizer()
    microphone = sr.Microphone()

    print("Aguardando comando...")

    with microphone as source:
        recognizer.adjust_for_ambient_noise(source)  # Ajusta para o ruído ambiente
        audio = recognizer.listen(source)  # Ouve o áudio

    try:
        # Usando PocketSphinx para reconhecimento offline
        command = recognizer.recognize_sphinx(audio)
        print(f"Você disse: {command}")
        process_command(command.lower())
    except sr.UnknownValueError:
        print("Não consegui entender o áudio.")
    except sr.RequestError as e:
        print(f"Erro ao conectar ao serviço de reconhecimento: {e}")

if __name__ == "__main__":
    main()
