import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class OpenRouterError(Exception):
    pass


class OpenRouterClient:
    def __init__(self):
        self.base_url = settings.OPENROUTER_BASE_URL.rstrip("/")
        self.model = settings.OPENROUTER_MODEL
        self.timeout = settings.OPENROUTER_TIMEOUT

    def _headers(self) -> dict[str, str]:
        if not settings.OPENROUTER_API_KEY:
            raise OpenRouterError("OPENROUTER_API_KEY is not configured.")

        return {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://localhost",
            "X-Title": settings.OPENROUTER_APP_TITLE,
        }

    async def chat_completion(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = True,
    ) -> dict:
        payload: dict = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else settings.OPENROUTER_TEMPERATURE,
            "max_tokens": max_tokens or settings.OPENROUTER_MAX_TOKENS,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )

        if response.status_code >= 400:
            logger.error("OpenRouter error %s: %s", response.status_code, response.text)
            raise OpenRouterError(
                f"OpenRouter request failed ({response.status_code}): {response.text}"
            )

        data = response.json()
        if "error" in data:
            raise OpenRouterError(str(data["error"]))

        return data

    @staticmethod
    def extract_message_content(response: dict) -> str:
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenRouterError("Unexpected OpenRouter response format.") from exc

        if not content or not str(content).strip():
            raise OpenRouterError("OpenRouter returned empty content.")

        return str(content).strip()

    @staticmethod
    def extract_token_usage(response: dict) -> dict:
        usage = response.get("usage") or {}
        return {
            "prompt": usage.get("prompt_tokens", 0),
            "completion": usage.get("completion_tokens", 0),
            "total": usage.get("total_tokens", 0),
        }
