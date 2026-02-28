"""Local AgentCore integration test.

Starts the AgentCore server locally, runs endpoint checks, then shuts down.

Usage:
  cd backend
  python test_agentcore_local.py
"""

import sys
import time
import threading
import requests

sys.path.insert(0, ".")

PORT = 8099


def start_server():
    from app.agentcore import create_agentcore_app
    app = create_agentcore_app()
    if not app:
        print("[FAIL] Could not create AgentCore app — SDK missing?")
        sys.exit(1)
    app.run(port=PORT, host="127.0.0.1")


def run_tests():
    base = f"http://127.0.0.1:{PORT}"
    passed = 0
    failed = 0

    # Test 1: Health check
    print("\n[TEST 1] GET /ping")
    try:
        r = requests.get(f"{base}/ping", timeout=5)
        data = r.json()
        assert data.get("status") == "Healthy", f"Expected Healthy, got {data}"
        print(f"  PASS — status={data['status']}")
        passed += 1
    except Exception as e:
        print(f"  FAIL — {e}")
        failed += 1

    # Test 2: Status action via /invocations
    print("\n[TEST 2] POST /invocations (status)")
    try:
        r = requests.post(f"{base}/invocations", json={"action": "status"}, timeout=5)
        data = r.json()
        assert data.get("service") == "diverge-agentcore", f"Unexpected: {data}"
        print(f"  PASS — service={data['service']}")
        passed += 1
    except Exception as e:
        print(f"  FAIL — {e}")
        failed += 1

    # Test 3: Missing path_a/path_b validation
    print("\n[TEST 3] POST /invocations (validation — missing paths)")
    try:
        r = requests.post(f"{base}/invocations", json={"action": "debate", "user_context": {}}, timeout=5)
        data = r.json()
        assert "error" in data, f"Expected error, got {data}"
        print(f"  PASS — error={data['error']}")
        passed += 1
    except Exception as e:
        print(f"  FAIL — {e}")
        failed += 1

    # Test 4: Interjection without debate_id
    print("\n[TEST 4] POST /invocations (interject — missing debate_id)")
    try:
        r = requests.post(f"{base}/invocations", json={"action": "interject", "text": "hello"}, timeout=5)
        data = r.json()
        assert "error" in data or "Missing" in data.get("error", ""), f"Expected error, got {data}"
        print(f"  PASS — error={data.get('error')}")
        passed += 1
    except Exception as e:
        print(f"  FAIL — {e}")
        failed += 1

    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'='*40}")
    return failed == 0


if __name__ == "__main__":
    print(f"Starting AgentCore server on port {PORT}...")
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Wait for server startup
    for i in range(15):
        try:
            requests.get(f"http://127.0.0.1:{PORT}/ping", timeout=1)
            break
        except Exception:
            time.sleep(1)
    else:
        print("[FAIL] Server did not start within 15 seconds")
        sys.exit(1)

    print("Server is up!")
    success = run_tests()
    sys.exit(0 if success else 1)
