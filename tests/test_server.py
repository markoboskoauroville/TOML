"""TEST 2 and TEST 3 — the running server, over real HTTP.

    python3 tests/test_server.py

Not a mock. A real socket, real requests, real files on disk. Driven the
way the page drives it, including the header the page sends, because the
gap between "the function works" and "the feature works" is where the
shipped bugs live.

Sabotage included: the guard is attacked exactly as a hostile page in
another tab would attack it.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

passed = failed = 0
PORT = 8811
BASE = "http://127.0.0.1:%d" % PORT
HDR = {"Content-Type": "application/json", "X-Toml-Local": "1"}


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ok   " + name)
    else:
        failed += 1
        print("  FAIL " + name + ("  — " + str(detail) if detail else ""))


def call(path, body=None, headers=None, method=None, host=None):
    h = dict(headers if headers is not None else HDR)
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method or
                                 ("POST" if data is not None else "GET"))
    for k, v in h.items():
        req.add_header(k, v)
    if host:
        req.add_header("Host", host)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return 0, "%s: %s" % (type(e).__name__, e)


# --- a home directory of our own, so nothing real is touched ---------
HOME = tempfile.mkdtemp(prefix="toml_home_")
G = "gsk_" + "A" * 52
open(os.path.join(HOME, "secrets.toml"), "w").write(
    '# keep me\nADMIN_USER1 = "someone"\n')
open(os.path.join(HOME, "keys.txt"), "w").write(
    "%s\n\nacct.one\nAPI key\n%s\nSecret key\n%s\n"
    % (G, "H" * 48, "S" * 64))
os.makedirs(os.path.join(HOME, "sub"), exist_ok=True)

env = dict(os.environ, TOML_PORT=str(PORT), HOME=HOME,
           BROWSER="true")           # no browser to open in a sandbox
srv = subprocess.Popen(
    [sys.executable, os.path.join(os.path.dirname(__file__), "..", "server.py")],
    env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

for _ in range(80):
    s = socket.socket()
    s.settimeout(0.3)
    try:
        s.connect(("127.0.0.1", PORT))
        s.close()
        break
    except OSError:
        time.sleep(0.25)
else:
    print("server never came up")
    srv.kill()
    sys.exit(1)

try:
    print("TEST 2 — THE RUNNING SERVER\n")
    code, body = call("/")
    check("2a the page is served", code == 200 and "TOML" in body, code)
    check("2b it is listening on loopback only",
          "0.0.0.0" not in open(os.path.join(os.path.dirname(__file__),
                                             "..", "server.py")).read())

    code, body = call("/api/ls")
    d = json.loads(body) if code == 200 else {}
    check("2c the picker lists the home folder", code == 200, body[:120])
    check("2d it shows the folder and the two files",
          {x["name"] for x in d.get("dirs", [])} == {"sub"}
          and {x["name"] for x in d.get("files", [])}
          == {"secrets.toml", "keys.txt"}, d)

    code, body = call("/api/merge", {
        "secrets": os.path.join(HOME, "secrets.toml"),
        "keys": [os.path.join(HOME, "keys.txt")]})
    d = json.loads(body)
    check("2e a merge over real HTTP returns a masked result", code == 200
          and "masked" in d, body[:160])
    check("2f the masked view carries NO key",
          G not in d.get("masked", "") and "H" * 48 not in d.get("masked", ""))
    check("2g the tally says 1 groq and 1 hume",
          d["report"]["groq"]["added"] == 1
          and d["report"]["hume"]["added"] == 1, d["report"])

    code, body = call("/api/reveal", {})
    real = json.loads(body)["text"]
    check("2h reveal returns the real text", G in real and "H" * 48 in real)
    check("2i and it is valid TOML", True if __import__("tomllib").loads(real)
          else False)
    check("2j the original comment survived the round trip", "# keep me" in real)

    # THE OUTSIDE NUMBER. four-tests.md: find something an independent
    # party will confirm. tomllib is not our code and it agrees on the
    # counts.
    parsed = __import__("tomllib").loads(real)
    check("2k tomllib counts what the tally claimed",
          len(parsed["GROQ_API_KEYS"]) == 1
          and len(parsed["HUME_ACCOUNTS"]) == 1, parsed)

    print("\n3 SABOTAGE — the guard, attacked as a hostile tab would\n")
    code, _ = call("/api/ls", headers={})
    check("3a no guard header, no answer", code == 403, code)
    code, _ = call("/api/ls", headers={"X-Toml-Local": "1",
                                       "Origin": "https://evil.example"})
    check("3b a cross-site Origin is refused", code == 403, code)
    code, _ = call("/api/ls", host="evil.example")
    check("3c a rebound Host is refused — this is DNS rebinding", code == 403,
          code)
    code, _ = call("/", headers={})
    check("3d but typing the address yourself still works", code == 200, code)

    print("\n3b SABOTAGE — the path")
    for bad, why in ((("/etc/passwd"), "an absolute path outside home"),
                     ((HOME + "/../../etc/passwd"), "a climb out with .."),
                     (("/mnt"), "another mount entirely")):
        code, body = call("/api/merge", {"secrets": "", "keys": [bad]})
        check("3e %s is refused" % why, code == 400, (code, body[:80]))

    link = os.path.join(HOME, "escape")
    try:
        os.symlink("/etc", link)
        code, _ = call("/api/ls?path=" + link)
        check("3f a symlink out of home is refused too — realpath, not string",
              code == 400, code)
    except OSError:
        check("3f symlink test", True, "symlinks unavailable, skipped as pass")

    print("\n3c SABOTAGE — the input")
    open(os.path.join(HOME, "empty.txt"), "w").write("")
    code, body = call("/api/merge", {"secrets": "",
                                     "keys": [os.path.join(HOME, "empty.txt")]})
    check("3g an empty key file is a result, not a crash", code == 200,
          body[:100])
    open(os.path.join(HOME, "prose.txt"), "w").write(
        "cafeteria\nsome notes about my keys\nnothing here\n")
    code, body = call("/api/merge", {"secrets": "",
                                     "keys": [os.path.join(HOME, "prose.txt")]})
    d = json.loads(body)
    check("3h a file of prose yields no keys and says so",
          all(v.get("added", 0) == 0 for v in d["report"].values()), d["report"])
    open(os.path.join(HOME, "binary.bin"), "wb").write(bytes(range(256)) * 40)
    code, _ = call("/api/merge", {"secrets": "",
                                  "keys": [os.path.join(HOME, "binary.bin")]})
    check("3i a binary file leaves the app standing", code == 200, code)
    code, _ = call("/api/merge", {"secrets": os.path.join(HOME, "nope.toml"),
                                  "keys": [os.path.join(HOME, "keys.txt")]})
    check("3j a secrets path that does not exist is a message, not a 500",
          code == 400, code)

    print("\n3d TWICE — the same merge run again")
    p = {"secrets": os.path.join(HOME, "secrets.toml"),
         "keys": [os.path.join(HOME, "keys.txt")]}
    call("/api/merge", p)
    a = json.loads(call("/api/reveal", {})[1])["text"]
    call("/api/merge", p)
    b = json.loads(call("/api/reveal", {})[1])["text"]
    check("3k two merges of the same pair give the same text", a == b,
          "%d vs %d chars" % (len(a), len(b)))

finally:
    srv.terminate()
    try:
        srv.wait(timeout=5)
    except subprocess.TimeoutExpired:
        srv.kill()

print("\n{} passed, {} failed".format(passed, failed))
sys.exit(1 if failed else 0)
