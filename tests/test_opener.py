"""THE PAGE OPENS ITSELF — tests for opener.py and portpick.py.

    python3 tests/test_opener.py

TEST 1 is the choosing logic with everything faked, so each branch can be
driven on a machine that has none of these commands.

TEST 2 is real: a stand-in `termux-open-url` is put on the PATH, the
actual server is started by the actual entry point, and the test asserts
that the URL it was handed reaches that program AND that the port in it
is the port the server really bound. Nothing is called directly.

TEST 3 is the ugly cases, and the one that matters is `am` lying.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import opener        # noqa: E402
import portpick      # noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ok   " + name)
    else:
        failed += 1
        print("  FAIL " + name + ("  — " + str(detail) if detail else ""))


URL = "http://localhost:8099/"

# ---------------------------------------------------------------- 1 --
print("1 CHOOSING WHAT OPENS THE PAGE\n")

calls = []


def runner_ok(cmd):
    calls.append(cmd)
    return 0, "Starting: Intent { act=android.intent.action.VIEW }"


def runner_no_chrome(cmd):
    calls.append(cmd)
    return 0, "Error: Activity not started, unable to resolve Intent"


have_am = {"am"}
check("1a with am and Chrome present, Chrome is used",
      opener.open_page(URL, runner=runner_ok,
                       which=lambda c: c if c in have_am else None)
      == "am:com.android.chrome", calls[-1:] if calls else None)

# THE ONE THAT MATTERS. `am` prints its failure and exits ZERO. A chain
# that trusts the exit code reports success and opens nothing.
calls.clear()
got = opener.open_page(URL, runner=runner_no_chrome,
                       which=lambda c: c if c in have_am else None)
check("1b am exits 0 while saying Error — that is NOT a success",
      got is None, got)
check("1c and every Chrome package was tried before giving up",
      len(calls) == len(opener.CHROME_PKGS), len(calls))


def which_termux(c):
    return "/usr/bin/" + c if c == "termux-open-url" else None


spawned = []
_real_spawn = opener._spawn
opener._spawn = lambda cmd: (spawned.append(cmd), True)[1]
try:
    got = opener.open_page(URL, runner=runner_no_chrome, which=which_termux)
    check("1d when Chrome refuses, termux-open-url is next",
          got == "termux-open-url", got)
    check("1e and it is handed the url, not a shell string",
          spawned and spawned[-1] == ["termux-open-url", URL], spawned[-1:])

    spawned.clear()
    got = opener.open_page(URL, runner=runner_no_chrome,
                           which=lambda c: "/usr/bin/xdg-open"
                           if c == "xdg-open" else None)
    check("1f on a desktop it falls through to xdg-open", got == "xdg-open",
          got)
finally:
    opener._spawn = _real_spawn

# ---------------------------------------------------------------- 2 --
print("\n2 WAITING FOR THE PORT BEFORE OPENING\n")
check("2a a port nobody is serving is not 'ready'",
      opener.wait_for_port("127.0.0.1", 8, timeout=0.6) is False)

srv = socket.socket()
srv.bind(("127.0.0.1", 0))
live = srv.getsockname()[1]
srv.listen(1)
try:
    t0 = time.time()
    check("2b a port that IS accepting is seen at once",
          opener.wait_for_port("127.0.0.1", live, timeout=5) is True)
    check("2c and it does not sit out the whole timeout",
          time.time() - t0 < 1.5, "%.2fs" % (time.time() - t0))
finally:
    srv.close()

# ---------------------------------------------------------------- 3 --
print("\n3 THE PORT IS NEVER A REASON NOT TO START\n")
check("3a a free port is returned unchanged",
      portpick.pick("127.0.0.1", 8099)[0] in range(8099, 8115))

hog = socket.socket()
hog.bind(("127.0.0.1", 0))
taken = hog.getsockname()[1]
hog.listen(1)
try:
    port, note = portpick.pick("127.0.0.1", taken)
    check("3b a taken port moves to another one", port != taken, port)
    check("3c and it SAYS so, rather than opening somewhere silently",
          bool(note) and str(port) in note, note)
    check("3d is_free agrees the taken one is taken",
          portpick.is_free("127.0.0.1", taken) is False)
finally:
    hog.close()

# ---------------------------------------------------------------- 4 --
# The real thing. A stand-in opener on the PATH, the real server started
# the way the launcher starts it, and the URL checked against the port
# the server actually bound.
print("\n4 REAL — the server started for real opens the real page\n")

HOME = tempfile.mkdtemp(prefix="toml_open_")
BINDIR = os.path.join(HOME, "bin")
os.makedirs(BINDIR)
LOG = os.path.join(HOME, "opened.txt")
stub = os.path.join(BINDIR, "termux-open-url")
with open(stub, "w") as f:
    f.write("#!/bin/sh\nprintf '%s\\n' \"$1\" >> " + LOG + "\n")
os.chmod(stub, 0o755)

# Hold the preferred port, so this also proves the opener follows
# portpick to the port that was ACTUALLY bound rather than the wanted one.
hog2 = socket.socket()
hog2.bind(("127.0.0.1", 8099))
hog2.listen(1)

env = dict(os.environ, HOME=HOME, TOML_PORT="8099",
           PATH=BINDIR + os.pathsep + os.environ["PATH"])
proc = subprocess.Popen(
    [sys.executable, os.path.join(os.path.dirname(__file__), "..", "server.py")],
    env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
try:
    url = None
    for _ in range(120):
        if os.path.exists(LOG):
            url = open(LOG).read().strip().splitlines()[-1]
            break
        time.sleep(0.25)
    check("4a the server opened a page without being asked", bool(url), url)
    if url:
        port = int(url.rsplit(":", 1)[1].rstrip("/"))
        check("4b it did NOT use the port that was already taken",
              port != 8099, port)
        check("4c and the page it opened actually answers", True
              if urllib.request.urlopen(url, timeout=10).status == 200
              else False)
        # The outside number: the server's own page must be reachable at
        # exactly the URL that was handed to the browser.
        req = urllib.request.Request(
            url + "api/ls",
            headers={"X-Toml-Local": "1", "Origin": url.rstrip("/")})
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
        check("4d the guard accepts that url as its own Origin",
              "path" in d, d)
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    hog2.close()

print("\n{} passed, {} failed".format(passed, failed))
sys.exit(1 if failed else 0)
