import time

import httpx

BASE_URL = "https://api.voyageai.com/v1/embeddings"
DEFAULT_MODEL = "voyage-3"
EMBEDDING_DIMENSIONS = 1024  # voyage-3's output dimension — must match filing_chunks.embedding

# Voyage's free trial *without* a payment method on file caps at 3
# requests/minute and 10K tokens/minute — verified empirically: even a
# 20-chunk (~30K char) batch exceeded 10K TPM, so SEC filing text tokenizes
# less efficiently than a naive chars/4 estimate suggests. Adding a payment
# method jumps this to Tier 1 (2000 RPM / 8M TPM for voyage-3.5 — voyage-3
# should be comparable), so both knobs are configurable via Settings
# (VOYAGE_BATCH_SIZE / VOYAGE_MIN_SECONDS_BETWEEN_REQUESTS) rather than
# hardcoded, letting this scale up once billing is on the account without a
# code change. These defaults are the safe (slow) free-trial fallback.
DEFAULT_BATCH_SIZE = 5
DEFAULT_MIN_SECONDS_BETWEEN_REQUESTS = 25.0


class VoyageEmbeddingError(RuntimeError):
    """Voyage AI returned an error response."""


class VoyageEmbeddingClient:
    def __init__(
        self,
        api_key: str,
        http_client: httpx.Client | None = None,
        model: str = DEFAULT_MODEL,
        batch_size: int = DEFAULT_BATCH_SIZE,
        min_seconds_between_requests: float = DEFAULT_MIN_SECONDS_BETWEEN_REQUESTS,
    ):
        self._api_key = api_key
        self._http = http_client or httpx.Client(timeout=60.0)
        self._model = model
        self._batch_size = batch_size
        self._min_seconds_between_requests = min_seconds_between_requests
        self._last_request_at: float | None = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            vectors.extend(self._embed_batch(batch))
        return vectors

    def _throttle(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = time.monotonic() - self._last_request_at
        remaining = self._min_seconds_between_requests - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        self._throttle()
        self._last_request_at = time.monotonic()
        response = self._http.post(
            BASE_URL,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"input": batch, "model": self._model, "input_type": "document"},
        )
        if response.status_code != 200:
            raise VoyageEmbeddingError(
                f"Voyage AI request failed ({response.status_code}): {response.text}"
            )
        data = response.json()["data"]
        ordered = sorted(data, key=lambda item: item["index"])
        return [item["embedding"] for item in ordered]
