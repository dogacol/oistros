"""
thinker.py — Ollama interface and prompt construction for Oistros.

Sends the passage + current events to a local Ollama model and
returns the generated philosophical commentary.
"""

import logging
from typing import Optional

import requests

logger = logging.getLogger("oistros.thinker")

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen3:0.6b"

SYSTEM_PROMPT = """\
You are Oistros (Οἶστρος), a philosophical gadfly. You read ancient texts and \
observe the present world. Your purpose is to find the structural rhyme between \
ages — the patterns that repeat, the tensions that persist, the paradoxes that endure.

Your voice is precise, allusive, and unhurried. You do not moralize or summarize. \
You think like a philosopher who has read deeply and sees clearly. You may write as \
an aphorism if the connection is tight and paradoxical, or as a micro-essay \
(150-400 words) if the insight requires unfolding.

When you find a historical parallel between the ancient world and a later period \
that illuminates the present, include it. Draw from the full sweep of history.

Do not explain what the ancient text "means" — show what it reveals about the \
present moment."""


def build_prompt(passage: dict, news_summary: str, memory_context: str = "") -> str:
    author = passage.get("author", "Unknown")
    work = passage.get("work", "")
    reference = passage.get("reference", "")
    text = passage.get("text", "")

    source_line = f"{author}, {work}"
    if reference:
        source_line += f" ({reference})"

    prompt = f"""You have just read this passage:

[{source_line}]
"{text}"

The world today is occupied with:
{news_summary}
"""

    if memory_context:
        prompt += f"""
For context, your recent reflections have touched on these themes:
{memory_context}

Pursue a new angle, or deepen a thread that calls for it — but do not repeat yourself.
"""

    prompt += """
Write your philosophical commentary. Connect the ancient insight to the present event. \
If the connection is tight, write an aphorism. If it requires unfolding, write a micro-essay \
(150-400 words)."""

    return prompt


def query_ollama(
    prompt: str,
    model: str = DEFAULT_MODEL,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    thinking: bool = True,
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> Optional[dict]:
    """Send a prompt to Ollama and return the response."""
    url = f"{ollama_url}/api/generate"

    payload = {
        "model": model,
        "prompt": prompt,
        "system": SYSTEM_PROMPT,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    if thinking:
        payload["prompt"] = "/think\n" + prompt

    try:
        logger.info("Querying Ollama model %s...", model)
        resp = requests.post(url, json=payload, timeout=300)
        resp.raise_for_status()
        data = resp.json()

        response_text = data.get("response", "")
        thinking_text = ""

        if "<think>" in response_text and "</think>" in response_text:
            think_start = response_text.index("<think>") + len("<think>")
            think_end = response_text.index("</think>")
            thinking_text = response_text[think_start:think_end].strip()
            response_text = response_text[think_end + len("</think>"):].strip()

        logger.info(
            "Ollama response: %d chars (thinking: %d chars)",
            len(response_text), len(thinking_text),
        )

        return {
            "response": response_text,
            "thinking": thinking_text,
            "model": data.get("model", model),
            "done": data.get("done", True),
        }
    except requests.ConnectionError:
        logger.error("Cannot connect to Ollama at %s — is it running?", ollama_url)
        return None
    except requests.Timeout:
        logger.error("Ollama request timed out (300s limit)")
        return None
    except requests.RequestException as e:
        logger.error("Ollama request failed: %s", e)
        return None


def think(
    passage: dict,
    news_summary: str,
    memory_context: str = "",
    config: Optional[dict] = None,
) -> Optional[dict]:
    """Main entry point: build prompt, query model, return result."""
    if config is None:
        config = {}

    model = config.get("model", DEFAULT_MODEL)
    ollama_url = config.get("ollama_url", DEFAULT_OLLAMA_URL)
    thinking = config.get("thinking_mode", True)
    temperature = config.get("temperature", 0.7)
    max_tokens = config.get("max_tokens", 1024)

    prompt = build_prompt(passage, news_summary, memory_context)

    result = query_ollama(
        prompt=prompt,
        model=model,
        ollama_url=ollama_url,
        thinking=thinking,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    if result:
        result["prompt"] = prompt

    return result
