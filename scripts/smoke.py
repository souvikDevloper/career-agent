"""Post-deploy smoke test against the live URL. Prints GitHub annotations so results are visible in the run summary."""

import json
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1].rstrip("/")
failures = []


def call(method, path, body=None, token=None, expect=(200,)):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=40) as res:
            status, raw = res.status, res.read()
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read()
    ok = status in expect
    text = raw.decode("utf8", "ignore")
    print(f"::{'notice' if ok else 'error'}::{method} {path} -> {status} {text[:300]}")
    if not ok:
        failures.append(path)
    try:
        return json.loads(text)
    except ValueError:
        return text


for attempt in range(10):
    try:
        urllib.request.urlopen(BASE + "/api/public/health", timeout=20)
        break
    except Exception:
        time.sleep(15)

call("GET", "/api/public/health")
call("GET", "/api/public/status")
jobs = call("GET", "/portal/api/jobs")
print(f"::notice::portal jobs: {len(jobs.get('jobs', [])) if isinstance(jobs, dict) else 'n/a'}")
call("GET", "/api/me", expect=(401,))
sess = call("POST", "/api/public/demo-session", {}, expect=(201,))
if isinstance(sess, dict) and sess.get("id_token"):
    tok = sess["id_token"]
    me = call("GET", "/api/me", token=tok)
    op = call("POST", "/api/search", {"keywords": "backend intern", "client_request_id": f"smoke-{int(time.time())}"}, token=tok, expect=(202, 200))
    op_id = (op or {}).get("operation", {}).get("op_id") if isinstance(op, dict) else None
    status = None
    for _ in range(40):
        if not op_id:
            break
        time.sleep(3)
        o = call("GET", f"/api/operations/{op_id}", token=tok)
        status = o.get("operation", {}).get("status")
        if status in ("succeeded", "failed"):
            res = o["operation"].get("results", [])
            print(f"::notice::search {status}: " + json.dumps([{k: r.get(k) for k in ('score', 'extractor')} | {'title': r['job'].get('title')} for r in res])[:900])
            if status == "failed":
                print("::error::" + json.dumps(o["operation"].get("progress", []))[:600])
            break
    if status != "succeeded":
        failures.append("search")
if failures:
    print(f"::error::smoke failures: {failures}")
    sys.exit(1)
print("::notice::smoke test passed")
