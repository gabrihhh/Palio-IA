"""
test/stt.py — Calibração STT

Roda o Whisper sem wake word e imprime tudo que for reconhecido em tempo real.
Útil para ajustar WHISPER_SILENCE_THRESHOLD e verificar precisão PT-BR.

Uso:
  python test/stt.py

Env vars respeitadas:
  WHISPER_MODEL               (padrão: small)
  WHISPER_SILENCE_THRESHOLD   (padrão: 400)
  WHISPER_SILENCE_DURATION    (padrão: 0.8)
"""

import os
import sys
from datetime import datetime

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from modules.stt.whisper_backend import iniciar_loop_stt


def main():
    print("[STT] Iniciando calibração. Fale algo. Ctrl+C para sair.", flush=True)

    def on_texto(texto: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] \"{texto}\"", flush=True)

    try:
        iniciar_loop_stt(
            on_comando=on_texto,
            bypass_wake_word=True,
        )
    except KeyboardInterrupt:
        print("\n[STT] Encerrando.", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
