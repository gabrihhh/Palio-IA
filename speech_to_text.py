import os
import json
import sounddevice as sd
import vosk

# Define o modelo Vosk (baixe o modelo de https://alphacephei.com/vosk/models e extraia na pasta 'model')
MODEL_PATH = "model"
if not os.path.exists(MODEL_PATH):
    print(f"Baixando o modelo e extraindo para {MODEL_PATH}...")
    # Baixe o modelo manualmente e extraia na pasta "model"

# Carrega o modelo
model = vosk.Model(MODEL_PATH)

# Configura o reconhecimento de áudio (offline)
samplerate = 16000  # Taxa de amostragem
device = None       # Use 'None' para o dispositivo de áudio padrão

# Variável global para capturar comandos após a palavra "carro"
waiting_for_command = False

# Função para processar o áudio e identificar palavras
def recognize_speech():
    global waiting_for_command
    # Inicia o microfone
    with sd.InputStream(samplerate=samplerate, channels=1, dtype='int16', device=device, callback=callback):
        recognizer = vosk.KaldiRecognizer(model, samplerate)

        print("Diga 'carro' para iniciar comandos...")
        while True:
            data = queue.get()
            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                recognized_text = result['text']
                print("Você disse:", recognized_text)
                
                if "carro" in recognized_text:
                    print("Comando de ativação detectado: 'carro'. Aguardando comandos...")
                    waiting_for_command = True
                elif waiting_for_command:
                    perform_action(recognized_text)

# Callback de áudio (coleta o áudio do microfone em blocos)
def callback(indata, frames, time, status):
    if status:
        print(status)
    queue.put(bytes(indata))

# Fila de áudio
import queue
queue = queue.Queue()

# Função para realizar uma ação dependendo do comando falado após "carro"
def perform_action(text):
    global waiting_for_command
    if "ligar luz" in text:
        print("Ligando a luz...")
        # Código para acionar a luz
    elif "desligar luz" in text:
        print("Desligando a luz...")
        # Código para desligar a luz
    elif "música" in text:
        print("Reproduzindo música...")
        # Código para reproduzir música
    elif "parar" in text:
        print("Encerrando comandos.")
        waiting_for_command = False
    else:
        print("Comando não reconhecido.")

if __name__ == "__main__":
    recognize_speech()
