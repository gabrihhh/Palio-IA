"""
test/tts.py — Teste de voz (TTS)

Carrega o modelo piper e fala o conteúdo de um arquivo .txt ou texto inline.
Útil para validar qualidade de voz e medir latência no Rock Pi.

Uso:
  python test/tts.py arquivo.txt
  python test/tts.py "texto direto entre aspas"

Env vars respeitadas:
  PIPER_MODEL   (padrão: models/pt_BR-faber-medium.onnx)
"""

import os
import sys
import tempfile
import wave

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

import sounddevice as sd
import soundfile as sf
from piper import PiperVoice

PIPER_MODEL = os.getenv("PIPER_MODEL", os.path.join(_PROJECT_ROOT, "models", "pt_BR-faber-medium.onnx"))


def main():
    if len(sys.argv) < 2:
        print("Uso: python test/tts.py arquivo.txt")
        print("      python test/tts.py \"texto direto\"")
        sys.exit(1)

    arg = sys.argv[1]

    if os.path.isfile(arg):
        with open(arg, "r", encoding="utf-8") as f:
            texto = f.read().strip()
    else:
        texto = arg

    if not texto:
        print("[TTS] Texto vazio. Nada para falar.")
        sys.exit(1)

    print(f"[TTS] Carregando modelo: {PIPER_MODEL}", flush=True)
    voice = PiperVoice.load(PIPER_MODEL)

    print(f"[TTS] Falando: \"{texto[:80]}{'...' if len(texto) > 80 else ''}\"", flush=True)

    fd, tmp_wav = tempfile.mkstemp(suffix=".wav", prefix="palio_tts_")
    os.close(fd)
    try:
        with wave.open(tmp_wav, "wb") as wav_file:
            voice.synthesize_wav(texto, wav_file)
        data, samplerate = sf.read(tmp_wav)
        sd.play(data, samplerate)
        sd.wait()
    except Exception as e:
        print(f"[TTS] Erro: {e}", flush=True)
        sys.exit(1)
    finally:
        if os.path.exists(tmp_wav):
            os.remove(tmp_wav)

    print("[TTS] Concluído.", flush=True)


if __name__ == "__main__":
    main()
