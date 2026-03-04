"""
modules/llm/client.py

Cliente HTTP para o Ollama rodando localmente.

O Ollama deve estar instalado e rodando no mesmo dispositivo (Rock Pi 4B):
  ollama serve
  ollama pull llama3.2:3b

API utilizada: POST http://localhost:11434/api/chat
"""

import logging
import requests
from modules.llm.persona import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2:3b"
REQUEST_TIMEOUT = 30  # segundos — Ollama pode ser lento no primeiro token


class OllamaClient:
    """
    Cliente para o servidor Ollama local.

    Mantém o histórico de conversa para contexto multi-turno.
    O system prompt da persona Palio é injetado automaticamente.
    """

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model
        self._history: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        self._available = self._check_availability()

    def _check_availability(self) -> bool:
        """Verifica se o Ollama está rodando e o modelo está disponível."""
        try:
            response = requests.get(
                f"{OLLAMA_BASE_URL}/api/tags",
                timeout=3,
            )
            if response.status_code != 200:
                logger.warning("Ollama respondeu com status %d", response.status_code)
                return False

            models = [m["name"] for m in response.json().get("models", [])]
            if not any(self.model in m for m in models):
                logger.warning(
                    "Modelo '%s' não encontrado no Ollama. "
                    "Execute: ollama pull %s",
                    self.model,
                    self.model,
                )
                return False

            logger.info("Ollama disponível com modelo '%s'.", self.model)
            return True

        except requests.exceptions.ConnectionError:
            logger.warning(
                "Ollama não está rodando em %s. "
                "Execute: ollama serve",
                OLLAMA_BASE_URL,
            )
            return False
        except Exception as e:
            logger.warning("Erro ao verificar Ollama: %s", e)
            return False

    @property
    def available(self) -> bool:
        return self._available

    def chat(self, user_message: str) -> str:
        """
        Envia uma mensagem ao Ollama e retorna a resposta da persona Palio.

        Mantém histórico de conversa para contexto.
        Se o Ollama não estiver disponível, retorna uma resposta de fallback.
        """
        if not self._available:
            return "Meu cérebro tá offline agora. Só consigo fazer coisas básicas."

        self._history.append({"role": "user", "content": user_message})

        try:
            response = requests.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": self.model,
                    "messages": self._history,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 150,  # máx tokens — respostas curtas para TTS
                    },
                },
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()

            reply = response.json()["message"]["content"].strip()
            self._history.append({"role": "assistant", "content": reply})

            # Limita histórico para não estourar contexto (mantém system + 20 turnos)
            if len(self._history) > 41:
                self._history = [self._history[0]] + self._history[-40:]

            return reply

        except requests.exceptions.Timeout:
            logger.error("Timeout ao aguardar resposta do Ollama.")
            return "Demorei demais pra pensar. Pode repetir?"
        except Exception as e:
            logger.error("Erro na chamada ao Ollama: %s", e)
            return "Deu um problema aqui. Tenta de novo."

    def reset_history(self) -> None:
        """Limpa o histórico de conversa, mantendo apenas o system prompt."""
        self._history = [{"role": "system", "content": SYSTEM_PROMPT}]
        logger.info("Histórico de conversa resetado.")
