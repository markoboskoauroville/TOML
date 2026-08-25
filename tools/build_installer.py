#!/usr/bin/env python3
"""Build 1-toml-v1-termux.sh from the source files in this repository.

ONE REPOSITORY, NOT TWO COPIES. MANTRA_MANIFEST README rule 1: the first
plan for MA_READER_ENGINE was a canonical folder plus a rule about
keeping copies in step, and it was rejected, correctly — two copies with
a synchronisation rule are still two copies and the rule is eventually
not followed.

The Termux convention in this account is a single self-contained .sh
(MAHA_TRANSCRIBE_TERMUX ships exactly one file). That means the Python
has to appear inside the shell script. So it is GENERATED from the real
files rather than pasted beside them, and the generated file carries the
hash of each source it was built from. If they drift, the check below
says so.

    python3 tools/build_installer.py          build
    python3 tools/build_installer.py --check  fail if the .sh is stale
"""

import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION = "1"
OUT = os.path.join(ROOT, "%s-toml-v%s-termux.sh" % (VERSION, VERSION))

SOURCES = ["parsers.py", "merge.py", "guard.py", "server.py",
           "templates/index.html"]

HEADER = r'''#!/data/data/com.termux/files/usr/bin/bash
###############################################################################
# TOML  -  installer for Termux (Android)            edition: v%s
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
# Install:  bash %s-toml-v%s-termux.sh      Run:  toml
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

printf '\n  '"$F"'TOML v%s'"$OFF"'\n\n'

PYBIN="$(command -v python 2>/dev/null || command -v python3 2>/dev/null)"
if [ -z "$PYBIN" ]; then
  printf '  '"$RED"'python is missing'"$OFF"'   run: pkg install python\n\n'
  exit 1
fi
printf '  '"$DIM"'python'"$OFF"'  %%s\n' "$($PYBIN -V 2>&1)"

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
''' % (VERSION, VERSION, VERSION, VERSION)

LAUNCHER = r'''
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
'''


def build():
    parts = [HEADER]
    hashes = []
    for rel in SOURCES:
        path = os.path.join(ROOT, rel)
        body = open(path, encoding="utf-8").read()
        hashes.append((rel, hashlib.sha256(body.encode()).hexdigest()[:12]))
        dest = "$APPDIR/" + rel
        eof = "SRC_" + rel.replace("/", "_").replace(".", "_").upper() + "_EOF"
        parts.append("\ncat > \"%s\" << '%s'\n%s\n%s\necho \"  %s written.\"\n"
                     % (dest, eof, body.rstrip("\n"), eof, rel))
    stamp = "\n# built from:\n" + "".join(
        "#   %-22s %s\n" % (r, h) for r, h in hashes)
    parts.insert(1, stamp)
    parts.append(LAUNCHER)
    text = "".join(parts)
    return text, hashes


def main():
    text, hashes = build()
    if "--check" in sys.argv:
        if not os.path.exists(OUT):
            print("STALE: %s does not exist" % os.path.basename(OUT))
            return 1
        cur = open(OUT, encoding="utf-8").read()
        if cur != text:
            print("STALE: %s does not match its sources. Rebuild it."
                  % os.path.basename(OUT))
            return 1
        print("installer is current, built from %d sources" % len(hashes))
        return 0
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(OUT, 0o755)
    print("wrote %s  (%d bytes)" % (os.path.basename(OUT), len(text)))
    for rel, h in hashes:
        print("  %-22s %s" % (rel, h))
    return 0


if __name__ == "__main__":
    sys.exit(main())
