"""TOML-UPDATE — one word, and it must actually update.

    python3 tests/test_update.py

The failure this file exists to prevent is named in
MANTRA_MANIFEST/modules/termux-app.md §10, and it is not a crash: an
updater that leaves the command behind and installs nothing **looks
exactly like nothing happening**. So the checks below do not ask "did it
exit zero". They ask what is on disk afterwards.

A real HTTP server on loopback serves the installer, and `toml-update` is
pointed at it with TOML_UPDATE_BASE. Nothing is mocked — the updater
runs curl against a real socket, exactly as it will against GitHub.
"""

import http.server
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
INSTALLER = os.path.join(ROOT, "toml-termux.sh")

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ok   " + name)
    else:
        failed += 1
        print("  FAIL " + name + ("  — " + str(detail) if detail else ""))


# --- a web server serving whatever we put in SERVE -------------------
SERVE = tempfile.mkdtemp(prefix="toml_serve_")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=SERVE, **k)

    def log_message(self, *a):
        pass


sock = socket.socket()
sock.bind(("127.0.0.1", 0))
SPORT = sock.getsockname()[1]
sock.close()
httpd = http.server.ThreadingHTTPServer(("127.0.0.1", SPORT), Quiet)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % SPORT


def fresh_home():
    """A home with the CURRENT version installed, and its edition faked
    to something old so an update is a real change."""
    home = tempfile.mkdtemp(prefix="toml_home_")
    os.makedirs(os.path.join(home, "usr", "bin"))
    run = os.path.join(home, "install.sh")
    with open(INSTALLER, encoding="utf-8") as f:
        body = f.read()
    body = body.replace("#!/data/data/com.termux/files/usr/bin/bash",
                        "#!/bin/bash", 1)
    with open(run, "w", encoding="utf-8") as f:
        f.write(body)
    env = dict(os.environ, HOME=home, PREFIX=os.path.join(home, "usr"))
    subprocess.run(["bash", run], env=env, capture_output=True)
    return home, env


def serve(text):
    with open(os.path.join(SERVE, "toml-termux.sh"), "w",
              encoding="utf-8") as f:
        f.write(text)


def run_update(env, yes=True, base=None):
    e = dict(env, TOML_UPDATE_BASE=base or BASE)
    if yes:
        e["TOML_UPDATE_YES"] = "1"
    # INVOKED THROUGH `bash`, NOT EXECUTED DIRECTLY, and that is not a
    # workaround. The launchers carry Termux's shebang —
    # /data/data/com.termux/files/usr/bin/bash — which is correct for the
    # only machine they are meant to run on and does not exist here. Check
    # 1f asserts that shebang is present, so this substitution can never
    # quietly become "the test runs a different program than the phone
    # does".
    p = subprocess.run(["bash", os.path.join(env["PREFIX"], "bin",
                                             "toml-update")],
                       env=e, capture_output=True, text=True, timeout=180)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


current = open(INSTALLER, encoding="utf-8").read()

print("1 THE COMMAND EXISTS AND IS INSTALLED BY THE INSTALLER\n")
home, env = fresh_home()
upd = os.path.join(env["PREFIX"], "bin", "toml-update")
check("1a toml-update was installed", os.path.isfile(upd))
check("1b it is executable", os.access(upd, os.X_OK))
check("1c so is toml", os.access(os.path.join(env["PREFIX"], "bin", "toml"),
                                 os.X_OK))
check("1d no half-written .new files were left behind",
      not [f for f in os.listdir(os.path.join(env["PREFIX"], "bin"))
           if f.endswith(".new")],
      os.listdir(os.path.join(env["PREFIX"], "bin")))
check("1e the installer kept a copy of itself, so the edition is readable",
      os.path.isfile(os.path.join(home, ".toml", "installer.sh")))
check("1f both commands carry the TERMUX shebang, not this machine's",
      all(open(os.path.join(env["PREFIX"], "bin", c)).readline().strip()
          == "#!/data/data/com.termux/files/usr/bin/bash"
          for c in ("toml", "toml-update")),
      open(os.path.join(env["PREFIX"], "bin", "toml")).readline())

print("\n2 IT ACTUALLY UPDATES — the failure §10 names\n")
# A version that is visibly different, so "did anything change" has an
# answer that is not a guess.
newer = current.replace("edition: v3", "edition: v99", 1).replace(
    'APP_VERSION = "v3"', 'APP_VERSION = "v99"', 1)
serve(newer)
code, out = run_update(env)
after = open(os.path.join(home, ".toml", "server.py"), encoding="utf-8").read()
check("2a it exits cleanly", code == 0, out[-300:])
check("2b THE FILES ON DISK CHANGED — v99 is installed",
      'APP_VERSION = "v99"' in after,
      [ln for ln in after.splitlines() if "APP_VERSION" in ln])
check("2c it said which edition it fetched", "v99" in out, out[-200:])
check("2d it said which edition was already there", "v3" in out, out[-200:])
check("2e the app still runs after the update",
      subprocess.run([sys.executable, "-c",
                      "import sys; sys.path.insert(0,'%s');"
                      % os.path.join(home, ".toml")
                      + "import parsers, merge, opener, portpick, guard"],
                     capture_output=True).returncode == 0)

print("\n3 THE THREE CHECKS, EACH ABLE TO FAIL ALONE\n")
for name, body, why in (
        ("a captive-portal page instead of the installer",
         "<html><body>Sign in to WiFi</body></html>\n", "size"),
        ("a file with no shebang",
         "echo hello\n" + "# pad\n" * 4000, "shebang"),
        ("half a file — cut mid-heredoc, which bash -n only WARNS about",
         current[:len(current) // 2], "parse"),
        ("a whole-looking file with the last line shaved off",
         "\n".join(current.splitlines()[:-1]) + "\n", "truncate"),
        # ONLY THE WARNINGS CHECK CATCHES THIS ONE. It is cut mid-heredoc
        # AND carries the sentinel, so the last-line check passes and
        # `bash -n` exits zero. four-tests.md: each check must be able to
        # fail while the others pass, and the first draft of these two
        # overlapped — removing the warnings check left everything green
        # because the sentinel was covering for it.
        ("cut mid-heredoc but WEARING the last line",
         current[:len(current) // 2] + "\n# TOML-INSTALLER-END v3\n",
         "warn")):
    home2, env2 = fresh_home()
    before = open(os.path.join(home2, ".toml", "server.py"),
                  encoding="utf-8").read()
    serve(body)
    code, out = run_update(env2)
    unchanged = open(os.path.join(home2, ".toml", "server.py"),
                     encoding="utf-8").read() == before
    check("3%s %s is refused" % (why[0], name), code == 1, code)
    check("3%s ... and NOTHING was changed" % why[0],
          unchanged and "nothing was changed" in out, out[-200:])
    shutil.rmtree(home2, ignore_errors=True)

print("\n4 IT ASKS FIRST\n")
home3, env3 = fresh_home()
before = open(os.path.join(home3, ".toml", "server.py"),
              encoding="utf-8").read()
serve(newer)
e = dict(env3, TOML_UPDATE_BASE=BASE)
p = subprocess.run(["bash", os.path.join(env3["PREFIX"], "bin",
                                         "toml-update")],
                   env=e, input="n\n", capture_output=True, text=True,
                   timeout=180)
still = open(os.path.join(home3, ".toml", "server.py"),
             encoding="utf-8").read() == before
check("4a answering n changes nothing", still, "it installed anyway")
check("4b and it says so", "nothing was changed" in p.stdout, p.stdout[-200:])
check("4c the prompt was actually shown", "install it?" in p.stdout,
      p.stdout[-200:])

print("\n5 A DOWNLOAD THAT CANNOT BE REACHED\n")
home4, env4 = fresh_home()
before = open(os.path.join(home4, ".toml", "server.py"),
              encoding="utf-8").read()
code, out = run_update(env4, base="http://127.0.0.1:9/nothing")
check("5a a dead host is a message, not a traceback", code == 1, code)
check("5b nothing was changed",
      open(os.path.join(home4, ".toml", "server.py"),
           encoding="utf-8").read() == before)
check("5c and it names the private-repo case, which is the real one today",
      "private" in out.lower(), out[-300:])

print("\n6 THE FILENAME IS AN ADDRESS — it must not drift\n")
check("6a the installer is named toml-termux.sh",
      os.path.basename(INSTALLER) == "toml-termux.sh")
check("6b toml-update asks for exactly that name",
      'FILE="toml-termux.sh"' in current)
check("6c and there is only one installer in the repo",
      len([f for f in os.listdir(ROOT) if f.endswith("-termux.sh")]) == 1,
      [f for f in os.listdir(ROOT) if f.endswith("-termux.sh")])

httpd.shutdown()
print("\n{} passed, {} failed".format(passed, failed))
sys.exit(1 if failed else 0)
