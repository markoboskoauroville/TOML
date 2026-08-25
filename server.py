#!/usr/bin/env python3
"""TOML — merge a key export into a secrets file, on this phone only.

    toml            start it, open the page
    Q               quit

WHAT IT IS FOR. Baba has 21 Hume accounts, 5 Groq keys and more coming
every time he rotates. Streamlit wants them as TOML. Typing 21 pairs by
hand on a phone is not a thing anybody does twice, and pasting them into
a chat to have them formatted puts them in a transcript forever.

So the formatting happens HERE, on the device that already has the keys.
Pick the secrets file, pick the export, read the result, press copy,
paste it into Streamlit. Nothing leaves the phone. There is no network
call in this program at all — grep it.

VERSION 1.
"""

import os
import sys
import threading

from flask import Flask, jsonify, render_template, request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import guard          # noqa: E402
import merge as M     # noqa: E402
import opener         # noqa: E402
import parsers        # noqa: E402
import portpick       # noqa: E402

APP_VERSION = "v4"
HOST = "127.0.0.1"
WANTED_PORT = int(os.environ.get("TOML_PORT", "8099"))
# THE PORT ACTUALLY BOUND, filled in by main(). Everything that needs a
# port reads THIS, never WANTED_PORT — guard.check compares Origin
# against it, and told the wrong number it would refuse every request
# from the page it just opened.
PORT = WANTED_PORT
HOME = os.path.expanduser("~")

# A file bigger than this is not a key file. Reading a 2 GB video into
# memory to look for gsk_ would take the phone down.
MAX_BYTES = 4 * 1024 * 1024

app = Flask(__name__)

# THE LAST MERGE LIVES IN MEMORY, IN THIS PROCESS, AND NOWHERE ELSE.
# Not in a session cookie, not in a temp file, not in a log. Quitting the
# server is what deletes it. `toml` is a thing you run for ninety seconds
# and then close.
STATE = {"merged": "", "report": {}}


@app.before_request
def _guard():
    refused = guard.check(PORT)
    if refused:
        return refused


def storage_roots():
    """Every folder the picker may reach, resolved.

    HOME, plus whatever `termux-setup-storage` linked into ~/storage.

    THIS HAD TO WIDEN, AND HERE IS WHY. Baba asked for the picker to open
    in ~/storage/downloads. That is a SYMLINK, and it points at
    /storage/emulated/0/Download — outside HOME. `_safe` resolves links
    before comparing, on purpose, so the folder he asked for would have
    been refused by the guard and the picker would have opened on an
    error. Setting it as the default without widening the roots would
    have shipped an app that cannot start.

    So the roots are a LIST, and every entry is still a resolved absolute
    path that a candidate must sit under. ~/storage exists only because
    he ran `termux-setup-storage` himself, which is Android asking him
    the permission question directly — a better authority for "may this
    app read shared storage" than anything this code could invent.

    Read once at startup. Running `termux-setup-storage` while the server
    is up needs a restart, which is one word.
    """
    roots, seen = [], set()

    def add(p):
        rp = os.path.realpath(p)
        if rp not in seen and os.path.isdir(rp):
            seen.add(rp)
            roots.append(rp)

    add(HOME)
    shelf = os.path.join(HOME, "storage")
    if os.path.isdir(shelf):
        try:
            for name in sorted(os.listdir(shelf)):
                add(os.path.join(shelf, name))
        except OSError:
            pass
    return roots


ROOTS = storage_roots()


def start_dir():
    """Where the picker opens. Downloads if it exists, else home.

    The same chain MAHA_TRANSCRIBE_TERMUX uses for its export folder, and
    for the same reason: it must never hard-fail. A picker that opens
    somewhere useful beats one that opens on an error.
    """
    for c in (os.path.join(HOME, "storage", "downloads"),
              os.path.join(HOME, "Downloads"),
              os.path.join(HOME, "downloads")):
        if os.path.isdir(c):
            return os.path.realpath(c)
    return os.path.realpath(HOME)


START = start_dir()


def _safe(path):
    """Absolute, real, and under one of ROOTS.

    Resolves symlinks BEFORE comparing, because a link pointing at /etc
    passes a string check and fails the only check that matters. That is
    also exactly why ROOTS had to become a list rather than the check
    being loosened — a resolved path is still compared against a fixed
    set of resolved prefixes, and nothing else gets in.
    """
    p = os.path.realpath(os.path.expanduser(path or ""))
    for root in ROOTS:
        if p == root or p.startswith(root + os.sep):
            return p
    return None


@app.route("/")
def index():
    return render_template("index.html", version=APP_VERSION, port=PORT)


@app.route("/api/ls")
def ls():
    """The file picker. Directories first, then files, both sorted.

    Hidden entries are SHOWN — .streamlit is a hidden directory and it is
    the single most likely place he is going. A picker that hides the
    thing it is for is a picker nobody can use.
    """
    p = _safe(request.args.get("path") or START)
    if not p or not os.path.isdir(p):
        return jsonify(error="that folder is not one this app may read"), 400
    dirs, files = [], []
    try:
        for name in sorted(os.listdir(p), key=str.lower):
            full = os.path.join(p, name)
            try:
                if os.path.isdir(full):
                    dirs.append({"name": name, "path": full})
                elif os.path.getsize(full) <= MAX_BYTES:
                    files.append({"name": name, "path": full,
                                  "size": os.path.getsize(full)})
            except OSError:
                continue
    except PermissionError:
        return jsonify(error="cannot read that folder"), 403
    up = os.path.dirname(p)
    # The shortcuts, so a picker that opens in Downloads is not a picker
    # that can only see Downloads. Sent every time and rendered every
    # time — design-language.md §1: nothing appears, nothing disappears.
    shortcuts = [{"name": ("home" if r == os.path.realpath(HOME)
                           else os.path.basename(r) or r),
                  "path": r, "here": r == p}
                 for r in ROOTS]
    return jsonify(path=p, parent=(up if _safe(up) else None),
                   dirs=dirs, files=files, shortcuts=shortcuts)


def _read(path):
    p = _safe(path)
    if not p or not os.path.isfile(p):
        return None, "not a file this app may read"
    if os.path.getsize(p) > MAX_BYTES:
        return None, "too big to be a key file"
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read(), None
    except OSError as e:
        return None, type(e).__name__


@app.route("/api/merge", methods=["POST"])
def do_merge():
    body = request.get_json(silent=True) or {}
    base_path = body.get("secrets") or ""
    keys_paths = body.get("keys") or []
    if isinstance(keys_paths, str):
        keys_paths = [keys_paths]

    base = ""
    if base_path:
        base, err = _read(base_path)
        if err:
            return jsonify(error="secrets file: " + err), 400

    pairs, singles = [], {}
    seen_pair = set()
    for kp in keys_paths:
        text, err = _read(kp)
        if err:
            return jsonify(error="key file: " + err), 400
        p, s = parsers.parse(text)
        for rec in p:
            if rec["key"] not in seen_pair:
                seen_pair.add(rec["key"])
                pairs.append(rec)
        for prov, keys in s.items():
            got = singles.setdefault(prov, [])
            for k in keys:
                if k not in got:
                    got.append(k)

    merged, report = M.merge(base, pairs, singles,
                             include_unknown=bool(body.get("unknown")))
    STATE["merged"] = merged
    STATE["report"] = report
    return jsonify(masked=M.mask(merged), report=report,
                   lines=merged.count("\n"), chars=len(merged))


@app.route("/api/reveal", methods=["POST"])
def reveal():
    """The real text. Its own endpoint, so the page only holds keys in
    the clear at the moment they are actually being copied."""
    return jsonify(text=STATE["merged"])


@app.route("/api/quit", methods=["POST"])
def quit_():
    threading.Timer(0.3, lambda: os._exit(0)).start()
    return jsonify(ok=True)


def main():
    """Pick a port, start serving, and open the page by itself.

    THE ORDER IS THE POINT. v1 opened the browser on a one-second timer,
    which is a guess about how long a phone takes to bind a socket. Guess
    low and the page says "connection refused", and somebody who sees
    that closes the tab and does not try again. So the opener waits for a
    real connection to the port and only then opens anything.
    """
    global PORT
    try:
        import flask.cli
        flask.cli.show_server_banner = lambda *a, **k: None
    except Exception:                                        # noqa: BLE001
        pass

    PORT, note = portpick.pick(HOST, WANTED_PORT)
    url = "http://localhost:%d/" % PORT

    print("\n  TOML %s" % APP_VERSION)
    print("  %s" % url)
    if note:
        print("  %s" % note)
    ip = opener.lan_ip()
    if ip:
        print("  not on %s — this app answers loopback only, on purpose" % ip)

    def report(ready, opened, u):
        if not ready:
            print("  the server did not come up in time — open %s by hand" % u)
        elif opened:
            print("  opened in %s" % opened)
        else:
            print("  no browser would open. Open this by hand:\n  %s" % u)
            if opener.is_termux():
                print("  (pkg install termux-tools gives termux-open-url)")

    threading.Thread(target=opener.open_when_ready,
                     kwargs={"host": HOST, "port": PORT, "url": url,
                             "on_result": report},
                     daemon=True).start()

    print("  Ctrl-C to stop.\n")
    try:
        from waitress import serve
        serve(app, host=HOST, port=PORT, threads=4, _quiet=True)
    except ImportError:
        app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
