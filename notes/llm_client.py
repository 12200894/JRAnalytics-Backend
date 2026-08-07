"""
Client for the LLM service.

The model runs in its own process behind HTTP. Django never imports PyTorch and never
holds the 209 MB checkpoint in memory — that separation is what keeps CRUD responses fast
and lets the AI tier be deployed and scaled on its own.
"""

import requests
from django.conf import settings


class LLMUnavailable(Exception):
    """Raised when the LLM service cannot be reached or returns an error."""


def summarise(note_text: str) -> dict:
    """Send a patient note to the LLM service. Returns {daily, overall, refused, model_version}."""
    url = f"{settings.LLM_SERVICE_URL.rstrip('/')}/summarise"
    try:
        response = requests.post(url, json={"note": note_text},
                                 timeout=settings.LLM_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        raise LLMUnavailable(
            f"Cannot reach the LLM service at {settings.LLM_SERVICE_URL}. "
            "Start it with: uvicorn service:app --port 8001")
    except requests.exceptions.Timeout:
        raise LLMUnavailable(
            f"LLM service timed out after {settings.LLM_TIMEOUT_SECONDS}s. "
            "Beam search on CPU is slow; raise LLM_TIMEOUT_SECONDS or use a GPU.")
    except requests.exceptions.HTTPError as exc:
        raise LLMUnavailable(f"LLM service returned {exc.response.status_code}: "
                             f"{exc.response.text[:200]}")


def health() -> dict:
    """Ask the LLM service whether it is up and has the model loaded."""
    try:
        r = requests.get(f"{settings.LLM_SERVICE_URL.rstrip('/')}/health", timeout=5)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as exc:
        raise LLMUnavailable(str(exc))
