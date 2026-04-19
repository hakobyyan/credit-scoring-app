"""HTTP client for the BentoML scoring service.

Provides typed methods that call the unified ``/evaluate_customer`` and
``/health`` endpoints.  Raises specific exceptions instead of silently
returning default values.
"""

from __future__ import annotations

import logging

import requests

from config.settings import settings

logger = logging.getLogger(__name__)


# ── Custom exceptions ──

class ServiceUnavailableError(Exception):
    """Raised when the scoring service cannot be reached."""


class ScoringError(Exception):
    """Raised when the service returns a server-side error (5xx)."""


class ValidationError(Exception):
    """Raised when the service rejects input (422)."""

    def __init__(self, detail: str = ""):
        self.detail = detail
        super().__init__(detail)


# ── API client ──

class ScoringAPIClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: int | None = None,
    ):
        self._base_url = (base_url or settings.api_url).rstrip("/")
        self._timeout = timeout or settings.api_timeout

    # ── Public methods ──

    def evaluate_customer(self, payload: dict) -> dict:
        """Call the unified evaluation endpoint.

        Returns the full EvaluationResponse dict on success.
        Raises ServiceUnavailableError, ScoringError, or ValidationError.
        """
        url = f"{self._base_url}/evaluate_customer"
        return self._post(url, {"json_input": payload})

    def check_health(self) -> dict:
        """Call the /readyz built-in endpoint, then /health API for model info.

        Returns HealthResponse dict or raises ServiceUnavailableError.
        """
        readyz_url = f"{self._base_url}/readyz"
        health_url = f"{self._base_url}/health"
        try:
            # BentoML built-in readiness probe (GET)
            resp = requests.get(readyz_url, timeout=self._timeout)
            resp.raise_for_status()
        except requests.ConnectionError:
            raise ServiceUnavailableError("Cannot connect to scoring service")
        except requests.Timeout:
            raise ServiceUnavailableError("Health check timed out")
        except Exception as exc:
            raise ServiceUnavailableError(str(exc))

        # Fetch model info from our /health API (POST for BentoML api)
        try:
            resp = requests.post(health_url, json={}, timeout=self._timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            # Service is up but /health API failed — report degraded status
            logger.warning("Health endpoint failed: %s", exc)
            return {"status": "degraded", "model_loaded": True}

    # ── Internal ──

    def _post(self, url: str, json_body: dict) -> dict:
        try:
            resp = requests.post(url, json=json_body, timeout=self._timeout)
        except requests.ConnectionError:
            logger.error("Connection refused: %s", url)
            raise ServiceUnavailableError("Cannot connect to scoring service")
        except requests.Timeout:
            logger.error("Request timed out: %s", url)
            raise ServiceUnavailableError("Request timed out")

        if resp.status_code == 422:
            detail = resp.text
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                pass
            logger.warning("Validation error from %s: %s", url, detail)
            raise ValidationError(str(detail))

        if resp.status_code >= 500:
            body = resp.text[:2000]
            logger.error("Server error %d from %s: %s", resp.status_code, url, body)
            raise ScoringError(f"Service error: HTTP {resp.status_code}: {body}")

        try:
            resp.raise_for_status()
        except requests.HTTPError as exc:
            logger.error("HTTP error %d from %s: %s", resp.status_code, url, exc)
            raise ScoringError(f"Service error: HTTP {resp.status_code}")

        data = resp.json()
        if not isinstance(data, dict):
            raise ScoringError("Unexpected response format from service")
        return data
