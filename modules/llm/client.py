"""
modules/llm/client.py

Cliente HTTP para o Ollama rodando localmente.

O Ollama deve estar instalado e rodando no mesmo dispositivo (Rock Pi 4B):
  ollama serve
  ollama pull llama3.2:3b

API utilizada: POST http://localhost:11434/api/chat

Memória persistente: lê data/brain.md no boot e injeta no system prompt.
O LLM pode atualizar o brain via tags [MEMO: nome=X] e [MEMO: nota=X] embutidas
na resposta — o cliente extrai as tags antes de passar o texto para o TTS.
"""

import logging
import re
import requests
from pathlib import Path
from modules.llm.persona import SYSTEM_PROMPT, MEMORY_INSTRUCTIONS

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2:3b"
REQUEST_TIMEOUT = 30  # segundos — Ollama pode ser lento no primeiro token

_BRAIN_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "brain.md"
_MEMO_RE = re.compile(r'\[MEMO:\s*(\w+)=([^\]]+)\]')


class OllamaClient:
    """
    Cliente para o servidor Ollama local.

    Mantém o histórico de conversa para contexto multi-turno.
    O system prompt da persona Palio + memória persistente (brain.md) são injetados automaticamente.
    """

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model
        self._history: list[dict] = [
            {"role": "system", "content": self._build_system_prompt()}
        ]
        self._available = self._check_availability()

    # ------------------------------------------------------------------ #
    # Memória persistente                                                  #
    # ------------------------------------------------------------------ #

    def _load_brain(self) -> str:
        """Lê o conteúdo do brain.md, ignorando o header. Retorna string vazia se não existir."""
        if not _BRAIN_PATH.exists():
            return ""
        try:
            content = _BRAIN_PATH.read_text(encoding="utf-8").strip()
            lines = [l for l in content.split("\n") if not l.startswith("# ")]
            return "\n".join(lines).strip()
        except Exception as e:
            logger.warning("Erro ao ler brain.md: %s", e)
            return ""

    def _build_system_prompt(self) -> str:
        """Monta o system prompt completo: persona + instruções de memória + estado atual do brain."""
        brain = self._load_brain()
        memoria_atual = brain if brain else "(vazia)"
        return f"{SYSTEM_PROMPT}\n\n{MEMORY_INSTRUCTIONS}\n\nEstado atual da memória:\n{memoria_atual}"

    def _parse_memo_tags(self, text: str) -> tuple[str, list[tuple[str, str]]]:
        """
        Extrai tags [MEMO: key=value] do texto.
        Retorna (texto limpo para TTS, lista de (key, value)).
        """
        tags = _MEMO_RE.findall(text)
        clean = _MEMO_RE.sub("", text)
        clean = re.sub(r" {2,}", " ", clean).strip()
        return clean, tags

    def _update_brain(self, key: str, value: str) -> None:
        """Atualiza brain.md com a nova informação recebida via tag MEMO."""
        if not _BRAIN_PATH.exists():
            logger.warning("brain.md não encontrado em %s — pulando atualização.", _BRAIN_PATH)
            return

        try:
            content = _BRAIN_PATH.read_text(encoding="utf-8")

            if key == "nome":
                new_content = re.sub(
                    r"(^nome_dono:).*$",
                    rf"\1 {value.strip()}",
                    content,
                    flags=re.MULTILINE,
                )
                _BRAIN_PATH.write_text(new_content, encoding="utf-8")
                logger.info("Memória: nome_dono salvo como '%s'.", value.strip())

            elif key == "nota":
                # Coleta notas existentes e remove do conteúdo
                nota_lines = re.findall(r"^- .+$", content, flags=re.MULTILINE)
                content_sem_notas = re.sub(r"^- .+\n?", "", content, flags=re.MULTILINE)

                # Máximo 5 notas — descarta a mais antiga se necessário
                if len(nota_lines) >= 5:
                    nota_lines = nota_lines[1:]
                nota_lines.append(f"- {value.strip()}")

                notas_block = "\n".join(nota_lines)
                new_content = re.sub(
                    r"(^notas:\s*)$",
                    rf"\1\n{notas_block}",
                    content_sem_notas,
                    flags=re.MULTILINE,
                )
                _BRAIN_PATH.write_text(new_content, encoding="utf-8")
                logger.info("Memória: nota salva — '%s'.", value.strip())

        except Exception as e:
            logger.error("Erro ao atualizar brain.md: %s", e)

    # ------------------------------------------------------------------ #
    # Ollama                                                               #
    # ------------------------------------------------------------------ #

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
        Tags [MEMO: ...] são extraídas da resposta e gravadas em brain.md antes do TTS.
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

            raw_reply = response.json()["message"]["content"].strip()

            # Extrai e processa tags de memória antes de passar para o TTS
            reply, memo_tags = self._parse_memo_tags(raw_reply)
            for key, value in memo_tags:
                self._update_brain(key, value)

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
        """Limpa o histórico de conversa, relendo o brain.md atualizado."""
        self._history = [{"role": "system", "content": self._build_system_prompt()}]
        logger.info("Histórico de conversa resetado.")
