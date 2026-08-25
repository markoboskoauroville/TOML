"""THE PICKER'S ROOT — Downloads by default, and the guard that had to widen.

    python3 tests/test_roots.py

Baba asked for the picker to open in `~/storage/downloads`. On a phone
that is a SYMLINK to /storage/emulated/0/Download, outside HOME, and
`_safe` resolves links before comparing — so the folder he asked for was
refused by the very guard that makes this app safe.

Widening a security check to satisfy a feature request is exactly the
move that goes wrong quietly, so this file exists to hold the line: the
allowed roots are a fixed list of resolved paths, and everything below
proves that a link OUT of them is still refused.

A fake ~/storage tree is built here, so this runs on a machine with no
Termux and no Android.
"""

import importlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ok   " + name)
    else:
        failed += 1
        print("  FAIL " + name + ("  — " + str(detail) if detail else ""))


# --- a phone-shaped home ---------------------------------------------
BOX = tempfile.mkdtemp(prefix="toml_phone_")
HOME = os.path.join(BOX, "home")
SHARED = os.path.join(BOX, "emulated", "0")          # stands in for real
DL = os.path.join(SHARED, "Download")
OUTSIDE = os.path.join(BOX, "etc")
for d in (HOME, DL, OUTSIDE, os.path.join(HOME, "storage")):
    os.makedirs(d, exist_ok=True)
os.symlink(DL, os.path.join(HOME, "storage", "downloads"))
os.symlink(SHARED, os.path.join(HOME, "storage", "shared"))
open(os.path.join(DL, "Hume.txt"), "w").write("acct\nAPI key\nA\nSecret key\nB\n")
open(os.path.join(OUTSIDE, "passwd"), "w").write("root:x:0:0\n")
# the hostile one: a link INSIDE an allowed root, pointing out of every root
os.symlink(OUTSIDE, os.path.join(DL, "escape"))

os.environ["HOME"] = HOME
import server                                        # noqa: E402
importlib.reload(server)

print("1 THE ROOTS\n")
print("       roots: %s" % [os.path.basename(r) or r for r in server.ROOTS])
check("1a home is a root", os.path.realpath(HOME) in server.ROOTS)
check("1b the resolved Downloads target is a root",
      os.path.realpath(DL) in server.ROOTS, server.ROOTS)
check("1c shared storage is a root too", os.path.realpath(SHARED)
      in server.ROOTS, server.ROOTS)
check("1d nothing outside is a root", os.path.realpath(OUTSIDE)
      not in server.ROOTS)

print("\n2 WHERE IT OPENS — the thing that was asked for\n")
check("2a the picker starts in Downloads, not home",
      server.START == os.path.realpath(DL),
      (server.START, os.path.realpath(DL)))

print("\n3 THE GUARD STILL HOLDS — a wider root is not a loose one\n")
check("3a the Downloads symlink resolves and is allowed",
      server._safe(os.path.join(HOME, "storage", "downloads"))
      == os.path.realpath(DL))
check("3b a real file in Downloads is readable",
      server._safe(os.path.join(DL, "Hume.txt")) is not None)
check("3c an absolute path outside every root is refused",
      server._safe("/etc/passwd") is None)
check("3d that box's own outside folder is refused",
      server._safe(OUTSIDE) is None)
check("3e a .. climb out of Downloads is refused",
      server._safe(os.path.join(DL, "..", "..", "etc")) is None)
# THE ONE THAT MATTERS: a link sitting inside an allowed root, pointing
# out of all of them. A string check would let this through.
check("3f a SYMLINK inside Downloads pointing outside is refused",
      server._safe(os.path.join(DL, "escape")) is None,
      server._safe(os.path.join(DL, "escape")))
check("3g and so is a file reached through it",
      server._safe(os.path.join(DL, "escape", "passwd")) is None)

print("\n4 WITH NO ~/storage AT ALL — a phone before termux-setup-storage\n")
BARE = tempfile.mkdtemp(prefix="toml_bare_")
os.environ["HOME"] = BARE
importlib.reload(server)
check("4a home is the only root", server.ROOTS == [os.path.realpath(BARE)],
      server.ROOTS)
check("4b so the picker opens in home, not on an error",
      server.START == os.path.realpath(BARE))
check("4c and /etc is still refused", server._safe("/etc") is None)

print("\n5 REAL — the running server, driven over HTTP\n")
os.environ["HOME"] = HOME
PORT = 8817
env = dict(os.environ, HOME=HOME, TOML_PORT=str(PORT), BROWSER="true")
proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "server.py")],
                        env=env, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)


def call(path):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path),
                                 headers={"X-Toml-Local": "1"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:                                   # noqa: BLE001
        return 0, {"err": str(e)}


try:
    for _ in range(60):
        code, _d = call("/api/ls")
        if code == 200:
            break
        time.sleep(0.25)
    code, d = call("/api/ls")
    check("5a the picker answers with no path given", code == 200, code)
    check("5b and it is showing Downloads", d.get("path")
          == os.path.realpath(DL), d.get("path"))
    check("5c the key export is listed there",
          "Hume.txt" in [f["name"] for f in d.get("files", [])], d.get("files"))
    names = [s["name"] for s in d.get("shortcuts", [])]
    check("5d the shortcuts include a way back to home", "home" in names, names)
    check("5e the one you are in is marked, not hidden",
          any(s["here"] for s in d.get("shortcuts", [])), d.get("shortcuts"))
    code, _ = call("/api/ls?path=" + os.path.join(DL, "escape"))
    check("5f browsing the escape link is refused over HTTP", code == 400, code)
    code, _ = call("/api/ls?path=/etc")
    check("5g and so is /etc", code == 400, code)
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()

print("\n{} passed, {} failed".format(passed, failed))
sys.exit(1 if failed else 0)
