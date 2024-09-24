import pyaudio
import vosk
import json

# Define o modelo Vosk offline
MODEL_PATH = "model"
model = vosk.Model(MODEL_PATH)

# Configurações de áudio
RATE = 16000
CHUNK = 1024

# Inicia PyAudio
p = pyaudio.PyAudio()

# Abre o stream de áudio
stream = p.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True, frames_per_buffer=CHUNK)
stream.start_stream()

recognizer = vosk.KaldiRecognizer(model, RATE)
waiting_for_command = False

print("Diga 'carro' para iniciar os comandos.")

while True:
    data = stream.read(CHUNK)
    if recognizer.AcceptWaveform(data):
        result = json.loads(recognizer.Result())
        recognized_text = result['text']
        print("Você disse:", recognized_text)
        
        if "carro" in recognized_text:
            print("Comando de ativação detectado: 'carro'. Aguardando comandos...")
            waiting_for_command = True
        elif waiting_for_command:
            # Adicione aqui as ações a serem realizadas após o comando "carro"
            if "ligar luz" in recognized_text:
                print("Ligando a luz...")
            elif "desligar luz" in recognized_text:
                print("Desligando a luz...")
            elif "música" in recognized_text:
                print("Reproduzindo música...")
            elif "parar" in recognized_text:
                print("Parando comandos.")
                waiting_for_command = False
