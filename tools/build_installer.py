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
VERSION = "3"
# THE FILENAME IS FROZEN, and that is deliberate.
#
# MANTRA_MANIFEST/modules/termux-app.md §11: versioning.md wants the whole
# number at both ends of the filename, and that is right for an artefact
# DOWNLOADED BY HAND. It is wrong for one FETCHED BY NAME by an updater —
# `toml-update` asks for this exact path, so renaming it on every build
# would break the one command Baba actually types.
#
# So the name is an address and never changes. The version lives in the
# `edition: v<n>` line inside the file, in APP_VERSION in server.py, and in
# the banner. tools/bump.py keeps those in step.
OUT = os.path.join(ROOT, "toml-termux.sh")

SOURCES = ["parsers.py", "merge.py", "guard.py", "portpick.py",
           "opener.py", "server.py", "templates/index.html"]

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
''' % (VERSION, VERSION)

LAUNCHER = r'''
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
# TOML-INSTALLER-END v__V__
'''.replace("__V__", VERSION)


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
