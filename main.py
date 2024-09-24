import pyttsx3
import os
import asyncio

async def falar(res):
    # Inicializar o mecanismo TTS
    engine = pyttsx3.init()

    # Configurar a taxa de fala
    engine.setProperty('rate', 160)  # Ajuste a velocidade conforme necessário

    # Configurar o volume
    engine.setProperty('volume', 1)  # Volume entre 0 e 1

    # Salvar o áudio em um arquivo WAV
    engine.save_to_file(res, 'output.wav')

    # Executar o áudio
    engine.runAndWait()

    # Reproduzir o áudio
    try:
        import winsound
        await winsound.PlaySound('output.wav', winsound.SND_FILENAME)
    except ImportError:
        print(f"Por favor, instale o módulo 'winsound' para reprodução de áudio no Windows.")
    except Exception as e:
        print(f"Ocorreu um erro ao tentar reproduzir o áudio: {e}")

    # # Limpar o arquivo de áudio depois de reproduzir
    if os.path.exists('output.wav'):
        os.remove('output.wav')


async def main():
    while True:
        entrada_audio = ''
        entrada_audio = input('\n Ouvindo: \n')

        if entrada_audio.lower() == 'desligar':
            await falar('Desligândo')
        if entrada_audio.lower() == 'pausar':
            await falar('Pausândo')

asyncio.run(main())
        