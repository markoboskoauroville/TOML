#!/data/data/com.termux/files/usr/bin/bash
###############################################################################
# TOML  -  installer for Termux (Android)            edition: v4
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
# THE PAGE OPENS ITSELF. Type toml and the browser comes up. It tries Chrome
# by intent first, then termux-open-url, then the desktop openers - and it
# READS what `am` printed rather than its exit code, because `am` writes
# "Error: Activity not started" and exits zero anyway. It also waits for the
# port to really accept a connection before opening, so the page is never
# "connection refused".
#
# IT NEVER FAILS TO START ON A BUSY PORT. 8099, then the next fifteen, then
# whatever the system gives - and it says which, because a page that quietly
# opens somewhere else is its own confusion.
#
# ONE WORD TO UPDATE. `toml-update` fetches the current version and installs
# it, and it asks before it changes anything. It refuses a download that is
# the wrong size, does not start with a shebang, or does not parse - because
# a truncated installer that gets installed is worse than an update that
# failed and said so.
#
# Install:  bash toml-termux.sh      Run:  toml      Update:  toml-update
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

printf '\n  '"$F"'TOML v4'"$OFF"'\n\n'

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
#   merge.py               25e74178e595
#   guard.py               5a6014ea90c6
#   portpick.py            56d48285542b
#   opener.py              8dd59c03fa66
#   server.py              1ded1d9d7cd5
#   templates/index.html   2d1ea2db8ed3

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

Baba's secrets file holds usernames, sheet URLs, drive ids and comments
he wrote himself. A merge that parses TOML
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

cat > "$APPDIR/portpick.py" << 'SRC_PORTPICK_PY_EOF'
"""portpick.py — the app never fails to start because a port is taken.

LIFTED from `GDRIVE_DOWNLOADER_FLASK_MACOS/portpick.py`. Its reasoning
applies here word for word, and it matters MORE here, because Baba asked
for the page to open by itself. A server that refuses to start opens
nothing, and the thing most likely to be holding port 8099 is **this app,
still running from before** — so without this, the app would block on its
own success case and the error would tell him to go and edit something.

    IT NEVER GIVES UP. Preferred port, then the next fifteen, then
    whatever the operating system hands out. There is no path through
    this module that ends in "could not start".

WHAT IT MUST NOT DO is pick a port and let the rest of the app carry on
believing the old one. Two things depend on the real number:

    the opener    opens the port actually bound, or shows a dead page
    guard.check   compares Origin against the port. Told the wrong one,
                  it refuses every request from the page it just opened

So `pick()` returns the number and the caller uses THAT everywhere.
"""

import socket

MAX_TRIES = 16


def is_free(host, port, timeout=0.4):
    """Can we actually BIND it? Not "is something listening".

    Asking whether something is listening answers a different question: a
    socket in TIME_WAIT, or bound to another interface, or owned by
    another user, all answer "nothing is listening" and then refuse the
    bind. The only honest test is to try.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # NOT SO_REUSEADDR. With it this test can succeed on a port
        # another process is already serving from, and the server then
        # fails behind us.
        s.settimeout(timeout)
        s.bind((host, int(port)))
        return True
    except OSError:
        return False
    finally:
        s.close()


def whats_there(port, timeout=1.0):
    """A guess at what holds the port, for the message only. Never raises.

    A raw socket rather than urllib, so this can only ever speak HTTP to
    loopback — the same reasoning as the original: making a thing
    impossible beats arguing that it cannot happen.
    """
    try:
        port = int(port)
        if not (1 <= port <= 65535):
            return None
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect(("127.0.0.1", port))
            s.sendall(b"GET / HTTP/1.0\r\nHost: 127.0.0.1\r\n"
                      b"Connection: close\r\n\r\n")
            body = b""
            while len(body) < 4000:
                chunk = s.recv(2048)
                if not chunk:
                    break
                body += chunk
        finally:
            s.close()
        if not body:
            return None
        return "self" if b"<title>TOML</title>" in body else "something"
    except Exception:                                        # noqa: BLE001
        return None


def pick(host, preferred, tries=MAX_TRIES):
    """Find a port. Always returns (port, note).

    `note` is None when the preferred port was free, otherwise a sentence
    saying what happened — a page that quietly opens somewhere other than
    where he expects is its own confusion.
    """
    preferred = int(preferred or 8099)
    if is_free(host, preferred):
        return preferred, None

    holder = whats_there(preferred)
    if holder == "self":
        why = ("port %d is already being used by another copy of TOML"
               % preferred)
    elif holder == "something":
        why = "port %d is being used by another program" % preferred
    else:
        why = "port %d could not be opened" % preferred

    for offset in range(1, tries):
        candidate = preferred + offset
        if candidate > 65535:
            break
        if is_free(host, candidate):
            return candidate, "%s, so this one is on %d instead." % (why,
                                                                     candidate)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, 0))
        chosen = s.getsockname()[1]
    finally:
        s.close()
    return chosen, "%s, so this one is on %d instead." % (why, chosen)
SRC_PORTPICK_PY_EOF
echo "  portpick.py written."

cat > "$APPDIR/opener.py" << 'SRC_OPENER_PY_EOF'
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
SRC_OPENER_PY_EOF
echo "  opener.py written."

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
.picker{position:fixed;inset:0;background:var(--bg);z-index:9;
  padding:var(--gap);overflow:auto;overscroll-behavior:contain;display:none}
/* SOLID, NOT rgba(...,.97). Baba's screenshot at 04:58 on 25.8.2026 shows
   the whole page printed through the picker — the header, the section
   titles and the placeholder text all legible behind the folder list. A
   97% wash is not a background, it is a tint, and on a near-black page
   with sand-coloured text the remaining 3% is still readable. Anything
   that covers the page uses the page's own background colour. */
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
/* A shortcut is a place, so it is pressable; the one you are already in
   is dimmed rather than removed. §1 again. */
.chip.go{cursor:pointer;border:1px solid transparent}
.chip.go.here{opacity:.4;pointer-events:none}

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
  <div class="tally" id="shortcuts"></div>
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
  const S = el('shortcuts'); S.innerHTML = '';
  (d.shortcuts || []).forEach(r => {
    const c = document.createElement('span');
    c.className = 'chip go' + (r.here ? ' here' : '');
    c.textContent = r.name;
    c.onclick = () => browse(r.path);
    S.appendChild(c);
  });
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

# ------------------------------------------- replacing a RUNNING command ----
# toml-update is a shell script that runs THIS installer, so while this is
# writing, the old updater is still alive and bash is still reading it. A
# plain "cat >" truncates the file the running shell is reading from, and it
# carries on at the old byte offset into whatever is there now - either
# nothing, or the middle of a different line. Small files survive by luck,
# because bash had already buffered the whole thing. Luck is not a mechanism.
#
# So each command is written beside its own name and RENAMED over the top. A
# rename swaps the directory entry; the running shell keeps its open file and
# reads it to the end undisturbed. And nothing half-written is ever reachable
# under the real name, because the real name only appears once the file behind
# it is complete.
#
# Lifted from ma-reader-thermux. See MANTRA_MANIFEST/modules/termux-app.md 4.
BIN="${PREFIX:-/usr/local}/bin"
mkdir -p "$BIN"

put_cmd() {   # $1 = final path
  chmod +x "$1.new" 2>/dev/null || true
  mv -f "$1.new" "$1"
}

# a run that died between writing and renaming leaves these behind
for _c in toml toml-update; do rm -f "$BIN/$_c.new" 2>/dev/null || true; done

cat > "$BIN/toml.new" << 'LAUNCHEOF'
#!/data/data/com.termux/files/usr/bin/bash
# TOML - merge a key export into a secrets file. Loopback only.
APPDIR="$HOME/.toml"
PORT="${TOML_PORT:-8099}"
PYBIN="$(command -v python 2>/dev/null || command -v python3 2>/dev/null)"
TOML_PORT="$PORT" "$PYBIN" "$APPDIR/server.py"
LAUNCHEOF
put_cmd "$BIN/toml"

# ------------------------------------------------------------ toml-update --
cat > "$BIN/toml-update.new" << 'UPDEOF'
#!/data/data/com.termux/files/usr/bin/bash
# TOML - one word to get the current version.
#
# IT UPDATES. An earlier updater elsewhere in this account only left the
# command behind and did not install anything, "which looked exactly like
# nothing happening" (ma-reader-thermux/update.sh). This fetches and installs
# in the same run.
#
# IT ASKS FIRST, and it validates before it replaces anything. A truncated
# installer that gets installed is worse than an update that failed and said
# so - so on any doubt it prints "nothing was changed" and stops.
set -e
REPO="${TOML_REPO:-markoboskoauroville/TOML}"
BRANCH="${TOML_BRANCH:-main}"
FILE="toml-termux.sh"
BASE="${TOML_UPDATE_BASE:-https://raw.githubusercontent.com/$REPO/$BRANCH}"

if [ -t 1 ]; then
  F=$'[38;5;214m'; DIM=$'[0;90m'; GREEN=$'[1;32m'
  RED=$'[38;5;203m'; OFF=$'[0m'
else
  F=''; DIM=''; GREEN=''; RED=''; OFF=''
fi

edition_of() { grep -m1 'edition: v' "$1" 2>/dev/null | sed 's/.*edition: //' | tr -d ' 
'; }

HERE=""
[ -f "$HOME/.toml/installer.sh" ] && HERE="$(edition_of "$HOME/.toml/installer.sh")"
[ -z "$HERE" ] && HERE="$(grep -m1 'APP_VERSION = ' "$HOME/.toml/server.py" 2>/dev/null | sed 's/.*"\(v[0-9]*\)".*//')"

printf '
  '"$F"'TOML update'"$OFF"'
'
[ -n "$HERE" ] && printf '  '"$DIM"'you have'"$OFF"'  %s
' "$HERE"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

printf '  '"$DIM"'fetching'"$OFF"'  %s
' "$BASE/$FILE"
if ! curl -fsSL --retry 3 --connect-timeout 20 -o "$TMP/$FILE" "$BASE/$FILE"; then
  printf '  '"$RED"'could not download it.'"$OFF"'
'
  printf '  '"$DIM"'If TOML is still a private repository an anonymous download
'
  printf '  cannot work. Ask Claude to make it public, or pull it on the Mac
'
  printf '  and copy the file across.'"$OFF"'
'
  printf '  nothing was changed.

'
  exit 1
fi

# --- three checks, and each one can fail on its own ------------------------
SIZE=$(wc -c < "$TMP/$FILE" | tr -d ' ')
if [ "$SIZE" -lt 20000 ]; then
  printf '  '"$RED"'the download is only %s bytes.'"$OFF"' A captive portal page is
' "$SIZE"
  printf '  '"$DIM"'about that size; an installer is not.'"$OFF"'
'
  printf '  nothing was changed.

'; exit 1
fi
if ! head -1 "$TMP/$FILE" | grep -q '^#!'; then
  printf '  '"$RED"'that is not a script - no shebang on the first line.'"$OFF"'
'
  printf '  nothing was changed.

'; exit 1
fi
PARSE="$(bash -n "$TMP/$FILE" 2>&1)" || {
  printf '  '"$RED"'the download did not parse.'"$OFF"'
'
  printf '  nothing was changed.

'; exit 1
}
# bash -n WARNS about an unterminated heredoc and STILL EXITS ZERO, so a
# clean status is not enough. Any output at all is a reason to stop.
if [ -n "$PARSE" ]; then
  printf '  '"$RED"'the download parsed with warnings:'"$OFF"' %s
' "$PARSE"
  printf '  nothing was changed.

'; exit 1
fi
# AND THE SENTINEL, because bash -n IS NOT A COMPLETENESS CHECK. Measured
# 25.8.2026: this installer cut in half mid-heredoc only WARNED, exited
# zero, and installed half the app. ma-reader-thermux/update.sh has the
# same three checks and the same hole. A last line that can only exist
# when the file is whole answers the question bash -n cannot.
if ! tail -1 "$TMP/$FILE" | grep -q '^# TOML-INSTALLER-END'; then
  printf '  '"$RED"'the download stops early - its last line is missing.'"$OFF"'
'
  printf '  '"$DIM"'A truncated transfer, not a bad version.'"$OFF"'
'
  printf '  nothing was changed.

'; exit 1
fi

THERE="$(edition_of "$TMP/$FILE")"
printf '  '"$GREEN"'got'"$OFF"'       %s, %s bytes
' "${THERE:-unknown}" "$SIZE"

if [ -n "$HERE" ] && [ "$HERE" = "$THERE" ]; then
  printf '  '"$DIM"'that is the version you already have.'"$OFF"'
'
fi

if [ "${TOML_UPDATE_YES:-}" != "1" ]; then
  printf '
  install it? [y/N] '
  read -r ANS
  case "$ANS" in
    y|Y|yes|YES) ;;
    *) printf '  nothing was changed.

'; exit 0 ;;
  esac
fi

cp -f "$TMP/$FILE" "$TMP/run.sh"
bash "$TMP/run.sh"
UPDEOF
put_cmd "$BIN/toml-update"

# The installer keeps a copy of itself, so toml-update can read the edition
# that is actually installed rather than guessing from the app version.
cp -f "$0" "$HOME/.toml/installer.sh" 2>/dev/null || true

echo ""
printf "  ${GREEN:-}installed${OFF:-}  type ${KEY:-}toml${OFF:-} to run it\n"
printf "  ${DIM:-}update it any time with${OFF:-} ${KEY:-}toml-update${OFF:-}${DIM:-} - one word, it asks first${OFF:-}\n"
echo ""
echo "  The page opens by itself. No address to type."
echo ""
echo "  1  choose your secrets file      (or none, to start a fresh one)"
echo "  2  choose the exported key file  (Hume, Groq, or any of them)"
echo "  3  press merge, press copy, paste into Streamlit"
echo ""
echo "  Serves on 127.0.0.1:8099, or the next free port if that one is busy."
echo "  Not reachable from your Wi-Fi, on purpose."
echo "  Values are masked on screen; copy takes the real text either way."
echo "  Nothing is written to disk and nothing is sent anywhere."
echo "=========================================================="

# ---------------------------------------------------------------- the end --
# THE SENTINEL, and it exists because `bash -n` IS NOT A COMPLETENESS CHECK.
# Measured 25.8.2026: a copy of this installer cut in half mid-heredoc makes
# `bash -n` print "warning: here-document delimited by end-of-file" and EXIT
# ZERO. The truncated file passed the parse check and installed half the app.
# ma-reader-thermux/update.sh has the same three checks and the same hole.
#
# A last line that only exists when the file is whole answers the question
# `bash -n` cannot: did all of it arrive.
# TOML-INSTALLER-END v4
