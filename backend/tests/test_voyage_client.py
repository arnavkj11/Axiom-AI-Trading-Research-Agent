import json

import httpx
import pytest

from app.filings.voyage_client import VoyageEmbeddingClient, VoyageEmbeddingError


def _client_with_response(payload: dict, status_code: int = 200, batch_size: int = 64):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(status_code, json=payload)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    return VoyageEmbeddingClient(api_key="test-key", http_client=http_client, batch_size=batch_size)


def test_embed_returns_vectors_in_input_order():
    payload = {
        "data": [
            {"index": 0, "embedding": [0.1, 0.2]},
            {"index": 1, "embedding": [0.3, 0.4]},
        ]
    }
    client = _client_with_response(payload)

    vectors = client.embed(["first chunk", "second chunk"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]


def test_embed_batches_large_inputs():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body["input"])
        embeddings = [{"index": i, "embedding": [float(i)]} for i in range(len(body["input"]))]
        return httpx.Response(200, json={"data": embeddings})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = VoyageEmbeddingClient(api_key="test-key", http_client=http_client, batch_size=2)

    vectors = client.embed(["a", "b", "c"])

    assert len(calls) == 2
    assert calls[0] == ["a", "b"]
    assert calls[1] == ["c"]
    assert vectors == [[0.0], [1.0], [0.0]]


def test_embed_raises_on_error_response():
    payload = {"detail": "Invalid API key"}
    client = _client_with_response(payload, status_code=401)

    with pytest.raises(VoyageEmbeddingError):
        client.embed(["text"])


def test_embed_empty_list_returns_empty_without_request():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not make a request for empty input")

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = VoyageEmbeddingClient(api_key="test-key", http_client=http_client)

    assert not client.embed([])


def test_throttles_between_consecutive_batches(monkeypatch):
    sleep_calls = []
    monkeypatch.setattr("app.filings.voyage_client.time.sleep", sleep_calls.append)
    payload = {"data": [{"index": 0, "embedding": [0.0]}, {"index": 1, "embedding": [0.0]}]}
    client = _client_with_response(payload, batch_size=1)

    client.embed(["a", "b"])  # two texts, batch_size=1 -> two requests

    assert len(sleep_calls) == 1
    assert sleep_calls[0] > 0


def test_does_not_throttle_a_single_batch(monkeypatch):
    sleep_calls = []
    monkeypatch.setattr("app.filings.voyage_client.time.sleep", sleep_calls.append)
    payload = {"data": [{"index": 0, "embedding": [0.0]}]}
    client = _client_with_response(payload)

    client.embed(["a"])

    assert not sleep_calls


def test_min_seconds_between_requests_is_configurable(monkeypatch):
    sleep_calls = []
    monkeypatch.setattr("app.filings.voyage_client.time.sleep", sleep_calls.append)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.0]}]})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = VoyageEmbeddingClient(
        api_key="test-key", http_client=http_client, batch_size=1, min_seconds_between_requests=0.5
    )

    client.embed(["a", "b"])

    assert len(sleep_calls) == 1
    assert sleep_calls[0] == pytest.approx(0.5, abs=0.05)
