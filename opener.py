"""opener.py — the page opens itself.

Baba: *"I don't need to enter the IP address manually. It should, when I
run the server, kick it automatically."*

LIFTED FROM `ma-reader-thermux/3sh_i_ma_reader_v3_termux.sh` and
`MAHA_TRANSCRIBE_TERMUX`, which have both already been through this on a
real phone. Three things they paid for, and none of them is obvious:

**1. `webbrowser` does not work on Termux.** Python's `webbrowser` module
looks for desktop browsers and desktop environment variables. On Android
there is no `$BROWSER`, no `xdg-open` by default, and no browser on the
path — it finds nothing and returns False, silently. v1 of this app used
it, which is why the page never opened by itself.

**2. `am start` PRINTS ITS FAILURES AND STILL EXITS ZERO.** This is the
one that matters. Asking a package to open a URL when that package is not
installed returns success and writes `Error: Activity not started` to
stdout. A chain that checks the exit code walks away believing it opened
a browser. So the OUTPUT is read, not the status.

**3. Filter by package, never by activity.** `-p com.android.chrome`
rather than naming an activity, because Chrome's activity name has
changed between versions and the package name never has.

**AND: WAIT FOR THE PORT BEFORE OPENING.** v1 opened the browser on a
one-second timer, which is a guess about how long a phone takes to bind a
socket. Guess low and the browser shows "connection refused" — and a
person who sees that closes the tab and does not try again, so the app
appears broken on the one screen that matters. `wait_for_port` connects
for real, and only then does the page open. Both halves are needed: an
opener that fires too early is the same failure as one that never fires.
"""

import os
import shutil
import socket
import subprocess
import time

# Every Chrome that exists, in the order worth trying.
CHROME_PKGS = ("com.android.chrome", "com.chrome.beta",
               "com.chrome.dev", "com.chrome.canary")

# `am` writes these and exits 0 anyway.
AM_FAILURE_WORDS = ("error", "exception", "not found", "does not exist",
                    "unable to resolve")


def wait_for_port(host, port, timeout=20.0, step=0.15):
    """Block until something accepts on this port. True if it did.

    A real connection, not a sleep. `is_free` in portpick asks the
    opposite question and neither answers this one: what we need to know
    is that the server is ready to serve, and the only honest test is to
    connect to it.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.4)
        try:
            s.connect((host, port))
            return True
        except OSError:
            time.sleep(step)
        finally:
            s.close()
    return False


def _am_open(url, runner=None, which=None):
    """Chrome by package, reading the OUTPUT because the status lies.

    `which` is injectable because otherwise this branch is unreachable on
    any machine without `am` — which is every machine except a phone. A
    branch that cannot be exercised is a branch nobody has checked, and
    this is the branch carrying the lesson.
    """
    runner = runner or _run
    which = which or shutil.which
    if not which("am"):
        return None
    for pkg in CHROME_PKGS:
        code, out = runner(["am", "start", "-a", "android.intent.action.VIEW",
                            "-d", url, "-p", pkg])
        if code != 0:
            continue
        low = (out or "").lower()
        if any(w in low for w in AM_FAILURE_WORDS):
            continue
        return "am:" + pkg
    return None


def _run(cmd, timeout=8):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:                                   # noqa: BLE001
        return 1, "%s: %s" % (type(e).__name__, e)


def _spawn(cmd):
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        return True
    except Exception:                                        # noqa: BLE001
        return False


def open_page(url, runner=None, which=None):
    """Open `url`. Returns the name of what opened it, or None.

    Order: Chrome by intent, then the phone's default handler, then the
    desktop openers, so the same function works when this is run on a
    Mac. `webbrowser` is LAST and only as a courtesy — it is the one that
    does not work on the phone this app is for.
    """
    which = which or shutil.which
    got = _am_open(url, runner=runner, which=which)
    if got:
        return got
    for cmd in ("termux-open-url", "xdg-open", "open"):
        if which(cmd) and _spawn([cmd, url]):
            return cmd
    try:
        import webbrowser
        if webbrowser.open(url):
            return "webbrowser"
    except Exception:                                        # noqa: BLE001
        pass
    return None


def open_when_ready(host, port, url=None, timeout=20.0, on_result=None):
    """Wait for the server, then open the page. For a background thread."""
    url = url or "http://localhost:%d/" % port
    ready = wait_for_port(host, port, timeout=timeout)
    opened = open_page(url) if ready else None
    if on_result:
        on_result(ready, opened, url)
    return ready, opened


def lan_ip():
    """Best guess at this device's Wi-Fi address, for the banner ONLY.

    It is printed so he knows what NOT to expect: this app refuses any
    Host that is not loopback, so the Wi-Fi address will not work even
    though the phone has one. Saying so beats him trying it.
    """
    try:
        code, out = _run(["ip", "route", "get", "1"], timeout=3)
        if code == 0:
            parts = out.split()
            for i, tok in enumerate(parts):
                if tok == "src" and i + 1 < len(parts):
                    return parts[i + 1]
    except Exception:                                        # noqa: BLE001
        pass
    return None


def is_termux():
    return "com.termux" in os.environ.get("PREFIX", "") or \
        os.path.isdir("/data/data/com.termux")
