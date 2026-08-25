#!/data/data/com.termux/files/usr/bin/bash
###############################################################################
# TOML  -  installer for Termux (Android)            edition: v1
#
# WHAT THIS IS. A little Flask application that merges an exported key file
# into a secrets file and shows you the result as TOML, with a copy button.
# You paste that into Streamlit. That is the whole job.
#
# WHY IT EXISTS. 21 Hume accounts, each an API key AND a secret key. 5 Groq
# keys, and more every rotation. Typing those into a phone by hand is not a
# thing anybody does twice, and pasting them into a chat to have them
# formatted puts them in a transcript that cannot be unsent.
#
# So the formatting happens on the device that already has the keys.
#
# NOTHING LEAVES THE PHONE. There is no outbound network call in this program.
# It binds 127.0.0.1 only - not 0.0.0.0, unlike the transcription app, because
# a cafe network is a room full of strangers and this page holds a keyring.
# Three checks stop another browser tab reaching it: the Host header must be a
# loopback name (DNS rebinding), a present Origin must be this app, and every
# call that reads a file must carry a header a cross-site request cannot set.
#
# WHAT IT READS. Only inside your home directory, resolved through symlinks
# before the check, so a link pointing at /etc does not get you /etc.
#
# WHAT IT WRITES. Nothing. The merged text lives in the server process and
# goes when you quit it. It is not saved, not cached, not logged.
#
# ADDITIVE, NEVER DESTRUCTIVE. Your comments, your usernames, your SHEETS_URL
# come through byte for byte. A key already in the file is left alone. A key
# in the file but not in the export is NEVER removed - rotating means adding
# the new one here and revoking the old one at the provider.
#
# Install:  bash 1-toml-v1-termux.sh      Run:  toml
###############################################################################
set -e

APPDIR="$HOME/.toml"
mkdir -p "$APPDIR/templates"

if [ -t 1 ]; then
  F=$'\033[38;5;214m'; KEY=$'\033[1;37m'; DIM=$'\033[0;90m'
  GREEN=$'\033[1;32m'; RED=$'\033[1;31m'; OFF=$'\033[0m'
else
  F=''; KEY=''; DIM=''; GREEN=''; RED=''; OFF=''
fi

printf '\n  '"$F"'TOML v1'"$OFF"'\n\n'

PYBIN="$(command -v python 2>/dev/null || command -v python3 2>/dev/null)"
if [ -z "$PYBIN" ]; then
  printf '  '"$RED"'python is missing'"$OFF"'   run: pkg install python\n\n'
  exit 1
fi
printf '  '"$DIM"'python'"$OFF"'  %s\n' "$($PYBIN -V 2>&1)"

if ! $PYBIN -c "import flask" >/dev/null 2>&1; then
  printf '  '"$DIM"'flask'"$OFF"'   installing\n'
  pip install --no-cache-dir --upgrade flask waitress >/dev/null 2>&1 || true
fi
if $PYBIN -c "import flask" >/dev/null 2>&1; then
  printf '  '"$GREEN"'flask   ok'"$OFF"'\n'
else
  printf '  '"$RED"'flask   MISSING'"$OFF"'   run: pip install flask waitress\n'
fi
echo ""

# built from:
#   parsers.py             964a6e6ff972
#   merge.py               79f47a9c99ae
#   guard.py               5a6014ea90c6
#   server.py              82e3d3faa54f
#   templates/index.html   e8012937ed8d

cat > "$APPDIR/parsers.py" << 'SRC_PARSERS_PY_EOF'
"""parsers.py — turning an exported key file into records.

TWO PASSES, IN THIS ORDER, AND THE ORDER IS THE WHOLE DESIGN.

Pass 1 reads LABELS. Hume's dashboard export gives an account name, the
words "API key", the key, the words "Secret key", the secret. Both halves
are plain alphanumeric with NO prefix, so shape cannot tell them apart —
the labels are the only reliable signal. This is Key_Tester's KeyParser
pass 1 (MANTRA_MANIFEST/apis/hume.md, "File format"), ported rather than
re-derived.

Pass 2 reads SHAPE, and skips every token pass 1 already consumed. If it
ran first it would eat a Hume API key as an "unknown" 48-character token
and orphan its secret.

WHY NOT SPLIT ON WHITESPACE. secrets.md §2: these files are notes. They
hold account names, URLs with tracking parameters, blank lines. Splitting
on whitespace has produced genuine attempts to authenticate with the word
*cafeteria* — which is, as it happens, the name of one of Baba's real
Hume accounts. Shape takes the keys and leaves the prose.

A KNOWN FAULT THIS FIXES. TTT-LLL's import_keys has a generic fallback
that grabs any long alphanumeric token, and five AssemblyAI 32-hex keys
ended up sitting in the Speechify ring because of it. Here the generic
catch-all is a SEPARATE bucket called "unknown" that is never merged into
a named provider's list without being asked.
"""

import re

# --- shapes, most specific first ------------------------------------
# Order matters: sk-ant- must be tried before sk-, and sk_ before the
# loose catch-all.
SHAPES = [
    ("anthropic",  re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("gemini",     re.compile(r"\b(?:AQ\.[A-Za-z0-9._-]{20,}|AIza[A-Za-z0-9_-]{20,})")),
    ("groq",       re.compile(r"\bgsk_[A-Za-z0-9]{20,}")),
    ("openai",     re.compile(r"\bsk-(?!ant-)[A-Za-z0-9_-]{20,}")),
    ("speechify",  re.compile(r"\bsk_[A-Za-z0-9_-]{16,}")),
    ("assemblyai", re.compile(r"\b[0-9a-f]{32}\b")),
]

# The catch-all. Never merged anywhere by itself — it lands in "unknown"
# and the person decides. See the note about the five AssemblyAI keys.
LOOSE = re.compile(r"\b[A-Za-z0-9]{32,220}\b")

API_LABEL = "api key"
SECRET_LABEL = "secret key"


def _next_non_empty(lines, i):
    while i < len(lines) and not lines[i].strip():
        i += 1
    return i


def parse_pairs(text):
    """Pass 1. Labelled account pairs. Returns ([record], consumed_set).

    A record is {"provider","name","key","secret"}.

    Tolerates: any case of the labels, blank lines between a label and
    its value, and a missing account name (the account is still taken,
    named by its position, because losing a working key to a cosmetic
    gap would be the worse failure).
    """
    lines = text.splitlines()
    out, consumed, seen = [], set(), set()
    i, prev, n = 0, "", 0
    while i < len(lines):
        t = lines[i].strip()
        if t.lower() == API_LABEL:
            n += 1
            name = prev or ("account %d" % n)
            a = _next_non_empty(lines, i + 1)
            key = lines[a].strip() if a < len(lines) else ""
            k = a + 1
            while k < len(lines) and lines[k].strip().lower() != SECRET_LABEL:
                k += 1
            s = _next_non_empty(lines, k + 1)
            secret = (lines[s].strip()
                      if k < len(lines) and s < len(lines) else "")
            if key and secret:
                consumed.add(key)
                consumed.add(secret)
                if key not in seen:
                    seen.add(key)
                    out.append({"provider": "hume", "name": name,
                                "key": key, "secret": secret})
                i = s + 1
                prev = ""
                continue
        if t:
            prev = t
        i += 1
    return out, consumed


def parse_singles(text, consumed=()):
    """Pass 2. Bare tokens, by shape, skipping what pass 1 took.

    Returns {provider: [key, ...]} in file order, no duplicates.

    Groq's export is the simple case this exists for: five `gsk_` lines
    and nothing else. No labels, no names, no structure.
    """
    consumed = set(consumed)
    found, seen = {}, set()
    for provider, rx in SHAPES:
        for m in rx.finditer(text):
            tok = m.group(0)
            if tok in consumed or tok in seen:
                continue
            seen.add(tok)
            found.setdefault(provider, []).append(tok)
    # The catch-all, kept apart on purpose.
    for m in LOOSE.finditer(text):
        tok = m.group(0)
        if tok in consumed or tok in seen:
            continue
        if not (any(c.isdigit() for c in tok) and any(c.isalpha() for c in tok)):
            continue
        seen.add(tok)
        found.setdefault("unknown", []).append(tok)
    return found


def parse(text):
    """Both passes. Returns (pairs, singles)."""
    pairs, consumed = parse_pairs(text)
    return pairs, parse_singles(text, consumed)


def summarise(pairs, singles):
    """Counts and account names only. NEVER a key. Safe to log."""
    rows = []
    if pairs:
        rows.append(("hume", len(pairs), [p["name"] for p in pairs]))
    for provider, keys in sorted(singles.items()):
        rows.append((provider, len(keys), []))
    return rows
SRC_PARSERS_PY_EOF
echo "  parsers.py written."

cat > "$APPDIR/merge.py" << 'SRC_MERGE_PY_EOF'
"""merge.py — adding keys to a secrets file without rewriting it.

THE RULE THIS MODULE EXISTS TO KEEP:

    NOTHING THAT WAS IN THE FILE COMES OUT OF IT.

Baba's secrets file holds ADMIN_USER1, FREE_USER2, SHEETS_URL,
DRIVE_ROOT_ID and comments he wrote himself. A merge that parses TOML
into a dict and dumps it back would return a file that is *equivalent*
and not the same: comments gone, order shuffled, his spacing replaced by
a library's. He would paste it into Streamlit and lose the notes that
tell him which key is whose.

So the merge is SURGICAL. The original text is kept verbatim and only
two kinds of region are touched:

    GROQ_API_KEYS = [ ... ]     an array — the new values are appended
                                inside the existing brackets
    [[HUME_ACCOUNTS]] ...       array-of-tables — new blocks are appended
                                after the last existing one

Anything else in the file is copied through untouched, byte for byte.

ADDITIVE, NEVER DESTRUCTIVE. A key already present is left where it is
and reported as "already there". A key in the file but not in the export
is NEVER removed — rotation means adding the new one and revoking the old
at the provider, and a merge tool that silently drops keys would be doing
the revoking for him, in the wrong place, with no way back.

DEDUPED BY VALUE. The same key arriving twice — from two exports, or a
file merged into itself — is stored once. Merging the same pair of files
twice must produce the same output as merging them once, and there is a
test for exactly that.
"""

import re

ARRAY_PROVIDERS = {
    "groq": "GROQ_API_KEYS",
    "anthropic": "ANTHROPIC_API_KEYS",
    "gemini": "GEMINI_API_KEYS",
    "speechify": "SPEECHIFY_API_KEYS",
    "assemblyai": "ASSEMBLYAI_API_KEYS",
    "openai": "OPENAI_API_KEYS",
}

HUME_TABLE = "HUME_ACCOUNTS"


def _quoted_values(block):
    """Every "..." string inside a chunk of TOML text."""
    return re.findall(r'"([^"\\]*)"', block)


def _find_array(text, name):
    """(start, end, body) of `NAME = [ ... ]`, or None. Bracket-counted,
    so a `]` inside a string cannot end the array early."""
    m = re.search(r'^[ \t]*' + re.escape(name) + r'[ \t]*=[ \t]*\[',
                  text, re.M)
    if not m:
        return None
    i = text.index("[", m.start())
    depth, j, in_str = 0, i, False
    while j < len(text):
        c = text[j]
        if c == '"' and text[j - 1:j] != "\\":
            in_str = not in_str
        elif not in_str:
            if c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    return m.start(), j + 1, text[i + 1:j]
        j += 1
    return None


def _hume_blocks(text):
    """Every [[HUME_ACCOUNTS]] block, as (start, end, text)."""
    out = []
    pat = re.compile(r'^[ \t]*\[\[[ \t]*' + re.escape(HUME_TABLE)
                     + r'[ \t]*\]\][ \t]*$', re.M)
    # THE BUG THIS SHAPE FIXES, found by check 3m on 25.8.2026.
    # Searching for the next "[" from s+1 matched the SECOND bracket of
    # this block's own "[[", one character along. Every block came back
    # empty, so `existing()` found no keys, so merging the same file
    # twice appended all 21 accounts again. The block must be measured
    # from the END of its own header line.
    for m in pat.finditer(text):
        s = m.start()
        after = m.end()
        nxt = re.search(r'^[ \t]*\[', text[after:], re.M)
        e = (after + nxt.start()) if nxt else len(text)
        out.append((s, e, text[s:e]))
    return out


def existing(text):
    """Every key value already in the file, by provider. Values, because
    dedupe has to be on the key itself — a label can be edited."""
    have = {}
    for provider, name in ARRAY_PROVIDERS.items():
        got = _find_array(text, name)
        if got:
            have[provider] = set(_quoted_values(got[2]))
    hume = set()
    for _s, _e, block in _hume_blocks(text):
        m = re.search(r'^[ \t]*key[ \t]*=[ \t]*"([^"]*)"', block, re.M)
        if m:
            hume.add(m.group(1))
    have["hume"] = hume
    return have


def _esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _render_hume(rec):
    return ('[[%s]]\nname   = "%s"\nkey    = "%s"\nsecret = "%s"\n'
            % (HUME_TABLE, _esc(rec["name"]), _esc(rec["key"]),
               _esc(rec["secret"])))


def merge(base_text, pairs, singles, include_unknown=False):
    """Return (merged_text, report).

    report is {provider: {"added": n, "already": n, "names": [...]}} —
    counts and account names only, never a key.
    """
    text = base_text if base_text.endswith("\n") or not base_text \
        else base_text + "\n"
    have = existing(text)
    report = {}

    # --- the arrays -------------------------------------------------
    for provider, keys in sorted(singles.items()):
        if provider == "unknown" and not include_unknown:
            report["unknown"] = {"added": 0, "already": 0,
                                 "skipped": len(keys), "names": []}
            continue
        name = ARRAY_PROVIDERS.get(provider, provider.upper() + "_API_KEYS")
        mine = have.get(provider, set())
        new = [k for k in keys if k not in mine]
        report[provider] = {"added": len(new), "skipped": 0,
                            "already": len(keys) - len(new), "names": []}
        if not new:
            continue
        got = _find_array(text, name)
        if got:
            start, end, body = got
            inner = body.rstrip()
            sep = "" if not inner.strip() else \
                ("" if inner.rstrip().endswith(",") else ",")
            added = "".join('\n    "%s",' % _esc(k) for k in new)
            text = (text[:start] + name + " = [" + inner + sep + added
                    + "\n]" + text[end:])
        else:
            block = name + " = [\n" \
                + "".join('    "%s",\n' % _esc(k) for k in new) + "]\n"
            text = text.rstrip("\n") + "\n\n" + block

    # --- the account pairs ------------------------------------------
    mine = have.get("hume", set())
    new_pairs = []
    seen = set()
    for p in pairs:
        if p["key"] in mine or p["key"] in seen:
            continue
        seen.add(p["key"])
        new_pairs.append(p)
    report["hume"] = {"added": len(new_pairs), "skipped": 0,
                      "already": len(pairs) - len(new_pairs),
                      "names": [p["name"] for p in new_pairs]}
    if new_pairs:
        blocks = _hume_blocks(text)
        rendered = "\n".join(_render_hume(p) for p in new_pairs)
        if blocks:
            at = blocks[-1][1]
            head = text[:at].rstrip("\n")
            text = head + "\n\n" + rendered + text[at:]
        else:
            text = text.rstrip("\n") + "\n\n" + rendered
    if not text.endswith("\n"):
        text += "\n"
    return text, report


def mask(text):
    """The screen copy. Every quoted value longer than 12 characters is
    blanked — DENY BY DEFAULT, per secrets.md §2a, so a key format
    nobody has seen yet is masked too. The clipboard gets the real text;
    this is only what is drawn.
    """
    def one(m):
        v = m.group(1)
        if len(v) <= 12:
            return m.group(0)
        return '"' + v[:3] + "\u2026" + ("\u2022" * 8) + "\u2026" + v[-2:] + '"'
    return re.sub(r'"([^"\\]*)"', one, text)
SRC_MERGE_PY_EOF
echo "  merge.py written."

cat > "$APPDIR/guard.py" << 'SRC_GUARD_PY_EOF'
"""guard.py — a page holding real keys, open to nobody but this phone.

LIFTED, NOT RE-DERIVED. This is `localguard.py` from
GDRIVE_DOWNLOADER_FLASK_MACOS, which already has the reasoning and
already had its one real bug removed. MANTRA_MANIFEST README rule 1: take
the version that has already been hurt.

THE THREAT, AND IT IS NOT EXOTIC. Binding to 127.0.0.1 stops the network.
It does not stop a WEB PAGE. Any site open in another tab can make the
browser send requests to http://127.0.0.1:8099 in the background. Without
a check, that page could ask this app to read a file off the disk and
hand back its contents — and this app's whole job is reading files full
of API keys.

That is a worse case here than in the downloader it came from. There, a
hostile page could start a download. Here it could read the keyring.

    1  HOST        the Host header must be a loopback name. Stops DNS
                   rebinding: evil.com resolved to 127.0.0.1 really is a
                   local connection, but the browser still sends
                   "Host: evil.com". Binding does not catch that
    2  ORIGIN      an Origin or Referer that is present must be this app
    3  FETCH SITE  a custom header the page always sends and a
                   cross-site request cannot. A form POST cannot set
                   headers at all; a fetch that tries triggers a CORS
                   preflight that never gets an allow

GET on / passes with 1 and 2 only — typing the address yourself sends no
Origin and no custom header. Everything that READS A FILE needs all three.

NOT 0.0.0.0 IN THE LOOPBACK LIST. It was there by copy-and-paste in the
original and it was the one entry that would have mattered: 0.0.0.0 means
every interface, so accepting it as a loopback name lets a request that
arrived from the network past the first check.

AND THIS ONE SERVES 127.0.0.1 ONLY. The Termux app it is modelled on
(MAHA_TRANSCRIBE_TERMUX) binds 0.0.0.0 so any device on the Wi-Fi can
reach it, which is right for a transcription page and wrong for this. A
café network is a room full of strangers.
"""

from flask import jsonify, request

LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}
GUARD_HEADER = "X-Toml-Local"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
OPEN_ENDPOINTS = {"static", "index", "favicon_ico"}


def _host_ok(host_header):
    if not host_header:
        return False
    host = (host_header.rsplit(":", 1)[0]
            if host_header.count(":") == 1 else host_header)
    if host.startswith("[") and "]" in host:
        host = host[:host.index("]") + 1]
    return host in LOCAL_HOSTS


def _origin_ok(origin, port):
    if not origin:
        return True
    allowed = {"http://%s:%d" % (h, port)
               for h in ("127.0.0.1", "localhost", "[::1]")}
    return origin.rstrip("/") in allowed


def check(port):
    """Called from before_request. Returns a response to refuse, or None."""
    if not _host_ok(request.headers.get("Host", "")):
        return jsonify(error="not a local host"), 403

    origin = (request.headers.get("Origin")
              or request.headers.get("Referer") or "")
    if origin:
        base = origin
        if base.count("/") > 2:
            parts = base.split("/")
            base = parts[0] + "//" + parts[2]
        if not _origin_ok(base, port):
            return jsonify(error="not this app"), 403

    if request.endpoint in OPEN_ENDPOINTS and request.method in SAFE_METHODS:
        return None

    if not request.headers.get(GUARD_HEADER):
        return jsonify(error="not this page"), 403
    return None
SRC_GUARD_PY_EOF
echo "  guard.py written."

cat > "$APPDIR/server.py" << 'SRC_SERVER_PY_EOF'
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
import webbrowser

from flask import Flask, jsonify, render_template, request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import guard          # noqa: E402
import merge as M     # noqa: E402
import parsers        # noqa: E402

APP_VERSION = "v1"
HOST = "127.0.0.1"
PORT = int(os.environ.get("TOML_PORT", "8099"))
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


def _safe(path):
    """Absolute, real, and inside the home directory.

    Resolves symlinks BEFORE comparing, because a link in home pointing
    at /etc passes a string check and fails the only check that matters.
    """
    p = os.path.realpath(os.path.expanduser(path or ""))
    home = os.path.realpath(HOME)
    if p != home and not p.startswith(home + os.sep):
        return None
    return p


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
    p = _safe(request.args.get("path") or HOME)
    if not p or not os.path.isdir(p):
        return jsonify(error="not a folder inside home"), 400
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
    return jsonify(path=p, parent=(up if _safe(up) else None),
                   dirs=dirs, files=files)


def _read(path):
    p = _safe(path)
    if not p or not os.path.isfile(p):
        return None, "not a file inside home"
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
    try:
        import flask.cli
        flask.cli.show_server_banner = lambda *a, **k: None
    except Exception:
        pass
    url = "http://%s:%d/" % (HOST, PORT)
    print("\n  TOML %s   %s" % (APP_VERSION, url))
    print("  merges a key export into a secrets file. Nothing leaves this phone.")
    print("  Ctrl-C to stop.\n")
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        from waitress import serve
        serve(app, host=HOST, port=PORT, threads=4, _quiet=True)
    except ImportError:
        app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
SRC_SERVER_PY_EOF
echo "  server.py written."

cat > "$APPDIR/templates/index.html" << 'SRC_TEMPLATES_INDEX_HTML_EOF'
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>TOML</title>
<style>
/* design-language.md §3, the measured palette. Amber is the accent in
   every Mantra app and this one is no exception. */
:root{
  --bg:#0B0D10; --surface:#141A21; --slate:#23303D;
  --amber:#F59E0B; --amber-dim:#E8A64B; --sand:#F2DDB4;
  --red:#EF4444; --green:#22C55E;
  --gap:14px;                     /* §10 equal distances, everywhere */
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--bg);color:var(--sand);
  font:16px/1.5 -apple-system,system-ui,"Segoe UI",Roboto,sans-serif;
  -webkit-text-size-adjust:100%}
body{padding:var(--gap) var(--gap) 40px}

/* §10 the row has two ends and a middle */
header{display:flex;align-items:baseline;gap:var(--gap);
  margin:0 0 var(--gap)}
header h1{margin:0;font-size:22px;letter-spacing:.14em;color:var(--amber);
  font-weight:600}
header .mid{flex:1;font-size:13px;color:#8A93A0}
header .ver{font-size:13px;color:#8A93A0;font-variant-numeric:tabular-nums}

section{background:var(--surface);border-radius:12px;padding:var(--gap);
  margin:0 0 var(--gap)}
h2{margin:0 0 10px;font-size:13px;letter-spacing:.12em;text-transform:uppercase;
  color:var(--amber-dim);font-weight:600}

.slot{display:flex;align-items:center;gap:10px;min-height:44px}
.slot .path{flex:1;font-family:ui-monospace,Menlo,monospace;font-size:13px;
  color:var(--sand);word-break:break-all;opacity:.95}
.slot .path.empty{opacity:.45}

/* §1 nothing appears, nothing disappears. Every control is rendered from
   the first frame and dimmed with opacity + pointer-events, which do not
   touch layout, so the page never jumps. */
button{font:inherit;min-height:44px;padding:0 16px;border-radius:10px;
  border:1px solid var(--slate);background:var(--slate);color:var(--sand);
  cursor:pointer;transition:opacity .12s}
button.primary{background:var(--amber);border-color:var(--amber);color:#1A1206;
  font-weight:600}
button.ghost{background:transparent}
button[disabled],.off{opacity:.35;pointer-events:none}
button:active{transform:translateY(1px)}

.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.grow{flex:1}

/* the picker */
.picker{position:fixed;inset:0;background:rgba(11,13,16,.97);z-index:9;
  padding:var(--gap);overflow:auto;display:none}
.picker.on{display:block}
.picker .cwd{font-family:ui-monospace,Menlo,monospace;font-size:12px;
  color:#8A93A0;word-break:break-all;margin:0 0 10px}
.entry{display:flex;align-items:center;gap:12px;min-height:44px;
  padding:0 10px;border-radius:8px;cursor:pointer}
.entry:active{background:var(--slate)}
.entry .glyph{width:22px;text-align:center;color:var(--amber-dim)}
.entry .nm{flex:1;word-break:break-all}
.entry .sz{font-size:12px;color:#8A93A0;font-variant-numeric:tabular-nums}

textarea{width:100%;min-height:240px;background:#0E1318;color:var(--sand);
  border:1px solid var(--slate);border-radius:10px;padding:12px;
  font-family:ui-monospace,Menlo,monospace;font-size:13px;line-height:1.45;
  white-space:pre;overflow-wrap:normal;overflow-x:auto}

.tally{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 10px}
.chip{font-size:13px;padding:5px 11px;border-radius:999px;
  background:var(--slate);color:var(--sand)}
.chip b{color:var(--amber);font-variant-numeric:tabular-nums}
.chip.none{opacity:.5}

.note{font-size:13px;color:#8A93A0;margin:10px 0 0}
.note.warn{color:var(--amber-dim)}
.err{color:var(--red);font-size:14px;margin:10px 0 0;min-height:20px}
.ok{color:var(--green)}
</style>
</head>
<body>

<header>
  <h1>TOML</h1>
  <span class="mid">merge · format · copy</span>
  <span class="ver">{{ version }}</span>
</header>

<section>
  <h2>1 · your secrets file</h2>
  <div class="slot">
    <div class="path empty" id="p-sec">none chosen — a new file will be made</div>
    <button class="ghost" onclick="pick('sec')">choose</button>
  </div>
</section>

<section>
  <h2>2 · the key export</h2>
  <div class="slot">
    <div class="path empty" id="p-key">none chosen</div>
    <button class="ghost" onclick="pick('key')">choose</button>
  </div>
  <div class="row" style="margin-top:10px">
    <button class="primary grow" id="b-merge" disabled onclick="doMerge()">merge</button>
  </div>
  <p class="note">Hume pairs are read by their labels; Groq, Anthropic,
     Gemini and the rest by shape. Anything unrecognised is counted and
     left out.</p>
</section>

<section>
  <h2>3 · the result</h2>
  <div class="tally" id="tally"><span class="chip none">nothing merged yet</span></div>
  <textarea id="out" readonly spellcheck="false"
    placeholder="the merged TOML appears here"></textarea>
  <div class="row" style="margin-top:10px">
    <button class="primary grow" id="b-copy" disabled onclick="doCopy()">copy</button>
    <button class="ghost" id="b-eye" disabled onclick="toggleEye()">reveal</button>
  </div>
  <p class="note warn" id="masknote">Values are masked on screen. Copy takes
     the real text either way — you do not have to reveal to copy.</p>
  <div class="err" id="err"></div>
</section>

<div class="picker" id="picker">
  <div class="row" style="margin-bottom:10px">
    <button class="ghost" onclick="closePicker()">cancel</button>
    <span class="grow"></span>
    <button class="ghost" id="b-up" onclick="goUp()">up</button>
  </div>
  <p class="cwd" id="cwd"></p>
  <div id="list"></div>
</div>

<script>
const H = {'Content-Type':'application/json','X-Toml-Local':'1'};
let chosen = {sec:'', key:''};
let target = null, cwd = null, parent = null;
let masked = '', revealed = false;

function el(id){ return document.getElementById(id); }
function say(m, ok){ const e = el('err'); e.textContent = m||''; e.className = ok? 'err ok':'err'; }

async function jget(u){ const r = await fetch(u,{headers:H}); return r.json(); }
async function jpost(u,b){
  const r = await fetch(u,{method:'POST',headers:H,body:JSON.stringify(b||{})});
  return r.json();
}

/* ---- the picker ---- */
function pick(which){ target = which; el('picker').classList.add('on'); browse(null); }
function closePicker(){ el('picker').classList.remove('on'); }
function goUp(){ if(parent) browse(parent); }

async function browse(path){
  const d = await jget('/api/ls' + (path? ('?path='+encodeURIComponent(path)) : ''));
  if(d.error){ say(d.error); closePicker(); return; }
  cwd = d.path; parent = d.parent;
  el('cwd').textContent = d.path;
  el('b-up').classList.toggle('off', !d.parent);
  const L = el('list'); L.innerHTML = '';
  d.dirs.forEach(x => L.appendChild(row('▸', x.name, '', () => browse(x.path))));
  d.files.forEach(x => L.appendChild(row('·', x.name, kb(x.size), () => take(x.path))));
  if(!d.dirs.length && !d.files.length)
    L.innerHTML = '<p class="note">nothing readable here</p>';
}
function row(glyph, name, size, fn){
  const e = document.createElement('div');
  e.className = 'entry';
  e.innerHTML = '<span class="glyph"></span><span class="nm"></span><span class="sz"></span>';
  e.children[0].textContent = glyph;
  e.children[1].textContent = name;
  e.children[2].textContent = size;
  e.onclick = fn;
  return e;
}
function kb(n){ return n < 1024 ? n+' B' : Math.round(n/1024)+' KB'; }

function take(path){
  chosen[target] = path;
  const p = el(target === 'sec' ? 'p-sec' : 'p-key');
  p.textContent = path; p.classList.remove('empty');
  el('b-merge').disabled = !chosen.key;
  closePicker();
  say('');
}

/* ---- merge ---- */
async function doMerge(){
  say('');
  const d = await jpost('/api/merge', {secrets: chosen.sec, keys: [chosen.key]});
  if(d.error){ say(d.error); return; }
  masked = d.masked; revealed = false;
  el('out').value = masked;
  el('b-copy').disabled = false;
  el('b-eye').disabled = false;
  el('b-eye').textContent = 'reveal';
  tally(d.report, d.lines);
}

function tally(rep, lines){
  const T = el('tally'); T.innerHTML = '';
  let any = false;
  Object.keys(rep).sort().forEach(k => {
    const r = rep[k];
    if(!r.added && !r.already && !r.skipped) return;
    any = true;
    const c = document.createElement('span');
    c.className = 'chip';
    let s = k + ' <b>+' + r.added + '</b>';
    if(r.already) s += ' · ' + r.already + ' already there';
    if(r.skipped) s += ' · ' + r.skipped + ' unrecognised, left out';
    c.innerHTML = s;
    T.appendChild(c);
  });
  const c = document.createElement('span');
  c.className = 'chip'; c.innerHTML = '<b>' + lines + '</b> lines';
  T.appendChild(c);
  if(!any) T.innerHTML = '<span class="chip none">no keys found in that file</span>';
}

/* ---- reveal and copy ---- */
async function toggleEye(){
  if(revealed){
    el('out').value = masked; revealed = false;
    el('b-eye').textContent = 'reveal';
    el('masknote').textContent = 'Values are masked on screen. Copy takes the real text either way — you do not have to reveal to copy.';
    return;
  }
  const d = await jpost('/api/reveal');
  el('out').value = d.text; revealed = true;
  el('b-eye').textContent = 'hide';
  el('masknote').textContent = 'Real keys are on the screen now. Hide them before anyone looks over your shoulder.';
}

async function doCopy(){
  const d = await jpost('/api/reveal');
  const text = d.text || '';
  try{
    await navigator.clipboard.writeText(text);
    say('copied — ' + text.length + ' characters. Paste into Streamlit secrets.', true);
  }catch(e){
    /* A clipboard call that never answers is the fault four-tests.md
       names by name. Fall back to a selection he can copy by hand
       rather than leaving a dead button. */
    const t = el('out');
    const was = t.value, wasRev = revealed;
    t.value = text; t.removeAttribute('readonly');
    t.focus(); t.select(); t.setSelectionRange(0, text.length);
    say('the browser refused the clipboard — the text is selected, copy it by hand');
    setTimeout(() => { t.setAttribute('readonly',''); if(!wasRev) t.value = was; }, 15000);
  }
}
</script>
</body>
</html>
SRC_TEMPLATES_INDEX_HTML_EOF
echo "  templates/index.html written."

# ---------------------------------------------------------- global command --
BIN="${PREFIX:-/usr/local}/bin"
mkdir -p "$BIN"
cat > "$BIN/toml" << 'LAUNCHEOF'
#!/data/data/com.termux/files/usr/bin/bash
# TOML - merge a key export into a secrets file. Loopback only.
APPDIR="$HOME/.toml"
PORT="${TOML_PORT:-8099}"
PYBIN="$(command -v python 2>/dev/null || command -v python3 2>/dev/null)"
TOML_PORT="$PORT" "$PYBIN" "$APPDIR/server.py"
LAUNCHEOF
chmod +x "$BIN/toml"

echo ""
printf "  ${GREEN:-}installed${OFF:-}  type ${KEY:-}toml${OFF:-} to run it\n"
echo ""
echo "  1  choose your secrets file      (or none, to start a fresh one)"
echo "  2  choose the exported key file  (Hume, Groq, or any of them)"
echo "  3  press merge, press copy, paste into Streamlit"
echo ""
echo "  Serves on 127.0.0.1:8099. Not reachable from your Wi-Fi, on purpose."
echo "  Values are masked on screen; copy takes the real text either way."
echo "  Nothing is written to disk and nothing is sent anywhere."
echo "=========================================================="
