"""FastAPI HTTP-layer smoke test — no network calls, no provider keys
required. Complements eval_phase1-8.py (which test the pipeline itself)
by checking the serving layer (main.py) actually wires up and responds.
"""
import sys

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert body["knowledge_version"]
    return True


def test_version_ok():
    resp = client.get("/version")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["prompt_version"]
    assert "gemini" in body["active_providers"] or "groq" in body["active_providers"]
    return True


def test_ask_rejects_empty_question():
    resp = client.post("/ask", json={"question": ""})
    assert resp.status_code == 422, resp.text  # pydantic min_length violation
    return True


def test_security_headers_present():
    resp = client.get("/health")
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
    assert "x-request-id" in resp.headers
    return True


def test_stats_endpoint_ok():
    resp = client.get("/stats")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "requests" in body and "total_estimated_cost_usd" in body
    return True


def run():
    tests = [
        test_health_ok, test_version_ok, test_ask_rejects_empty_question,
        test_security_headers_present, test_stats_endpoint_ok,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"[PASS] {t.__name__}")
            passed += 1
        except AssertionError as exc:
            print(f"[FAIL] {t.__name__} — {exc}")
    print(f"\nAPI smoke checks: {passed}/{len(tests)} passed")
    return passed == len(tests)


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
