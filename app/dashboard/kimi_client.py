#!/usr/bin/env python3
"""
Kimi Client - Run this from Kimi to interact with Omni-Studio.
Usage:
  python3 kimi_client.py status          # Get Omni-Studio status
  python3 kimi_client.py swarm "objective" # Run swarm task
  python3 kimi_client.py agent atlas "message" # Talk to agent
  python3 kimi_client.py chat "message"    # Chat with LLM
  python3 kimi_client.py queue            # Get pending tasks
  python3 kimi_client.py complete <task_id> "result" # Complete a task
"""
import sys
import json
import requests

OMNI_URL = "http://127.0.0.1:8500"
DEFAULT_TIMEOUT = 30

def api(method, path, data=None):
    url = f"{OMNI_URL}{path}"
    if method == "GET":
        r = requests.get(url, timeout=DEFAULT_TIMEOUT)
    else:
        r = requests.post(url, data=data, timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    return r.json()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "status":
        print(json.dumps(api("GET", "/api/bridge/tasks"), indent=2))

    elif cmd == "swarm":
        obj = sys.argv[2] if len(sys.argv) > 2 else "Test objective"
        print(json.dumps(api("POST", "/api/bridge/kimi", {"task_type": "swarm", "payload": json.dumps({"objective": obj})}), indent=2))

    elif cmd == "agent":
        agent = sys.argv[2] if len(sys.argv) > 2 else "atlas"
        msg = sys.argv[3] if len(sys.argv) > 3 else "Hello"
        print(json.dumps(api("POST", "/api/bridge/kimi", {"task_type": "agent", "payload": json.dumps({"agent": agent, "message": msg})}), indent=2))

    elif cmd == "chat":
        msg = sys.argv[2] if len(sys.argv) > 2 else "Hello"
        print(json.dumps(api("POST", "/api/bridge/kimi", {"task_type": "chat", "payload": json.dumps({"message": msg})}), indent=2))

    elif cmd == "queue":
        print(json.dumps(api("GET", "/api/bridge/tasks"), indent=2))

    elif cmd == "complete":
        task_id = sys.argv[2] if len(sys.argv) > 2 else ""
        result = sys.argv[3] if len(sys.argv) > 3 else ""
        print(json.dumps(api("POST", "/api/bridge/complete", {"task_id": task_id, "result": result}), indent=2))

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
