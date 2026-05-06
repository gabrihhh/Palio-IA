"""
test/chat.py — Teste do Ollama (conversa direta LLM → TTS)

Dois modos de uso:

  Modo voz (sem argumentos):
    Fale qualquer coisa e o Palio responde por voz. Sem wake word.
    Útil para testar o ciclo completo STT → LLM → TTS.
    python test/chat.py

  Modo texto (com argumento):
    Passa o texto direto, Ollama processa e responde por voz. Sem STT.
    Útil para testar a persona e a qualidade da resposta sem microfone.
    python test/chat.py "qual é o seu nome?"

Usa a persona e o brain.md normalmente em ambos os modos.

Env vars respeitadas:
  PIPER_MODEL, WHISPER_MODEL, WHISPER_SILENCE_THRESHOLD, WHISPER_SILENCE_DURATION
"""

import os
import re
import sys
import tempfile
import wave
from datetime import datetime

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

import sounddevice as sd
import soundfile as sf
from piper import PiperVoice

from modules.llm.client import OllamaClient
from modules.stt.whisper_backend import iniciar_loop_stt

PIPER_MODEL = os.getenv("PIPER_MODEL", os.path.join(_PROJECT_ROOT, "models", "pt_BR-cadu-medium.onnx"))


def _limpar_markdown(texto: str) -> str:
    texto = re.sub(r'\*{1,3}(.+?)\*{1,3}', r'\1', texto)
    texto = re.sub(r'_{1,2}(.+?)_{1,2}', r'\1', texto)
    texto = re.sub(r'`{1,3}[^`]*`{1,3}', '', texto)
    texto = re.sub(r'^#{1,6}\s+', '', texto, flags=re.MULTILINE)
    texto = re.sub(r'^\s*[-*]\s+', '', texto, flags=re.MULTILINE)
    texto = re.sub(r'^\s*>\s+', '', texto, flags=re.MULTILINE)
    return texto.strip()


def _processar_e_falar(texto: str, llm: "OllamaClient", falar) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] Você: \"{texto}\"", flush=True)
    resposta = llm.chat(texto)
    resposta_limpa = _limpar_markdown(resposta)
    print(f"[{ts}] Palio: \"{resposta_limpa}\"", flush=True)
    falar(resposta_limpa)


def main():
    texto_arg = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else None

    print("[CHAT] Carregando modelo TTS...", flush=True)
    voice = PiperVoice.load(PIPER_MODEL)

    def falar(texto: str) -> None:
        fd, tmp_wav = tempfile.mkstemp(suffix=".wav", prefix="palio_tts_")
        os.close(fd)
        try:
            with wave.open(tmp_wav, "wb") as wav_file:
                voice.synthesize_wav(texto, wav_file)
            data, samplerate = sf.read(tmp_wav)
            sd.play(data, samplerate)
            sd.wait()
        except Exception as e:
            print(f"[CHAT] Erro TTS: {e}", flush=True)
        finally:
            if os.path.exists(tmp_wav):
                os.remove(tmp_wav)

    print("[CHAT] Conectando ao Ollama...", flush=True)
    llm = OllamaClient(model="llama3.2:3b")
    if not llm.available:
        print("[CHAT] Ollama indisponível. Verifique se 'ollama serve' está rodando.", flush=True)
        sys.exit(1)

    if texto_arg:
        # Modo texto: processa o argumento e sai
        _processar_e_falar(texto_arg, llm, falar)
        sys.exit(0)

    # Modo voz: loop STT → LLM → TTS sem wake word
    print("[CHAT] STT, TTS e LLM prontos. Fale algo. Ctrl+C para sair.\n", flush=True)

    try:
        iniciar_loop_stt(
            on_comando=lambda texto: _processar_e_falar(texto, llm, falar),
            bypass_wake_word=True,
        )
    except KeyboardInterrupt:
        print("\n[CHAT] Encerrando.", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
