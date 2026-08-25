#!/usr/bin/env python3
"""Bump the visible version of TOML. Run before every push.

    python3 tools/bump.py         v3 -> v4
    python3 tools/bump.py 10      set it outright

THE FILENAME NEVER CHANGES, and that is the point of this script existing.
`toml-update` fetches `toml-termux.sh` by that exact name, so renaming it on
every build would break the one command Baba actually types. The number lives
INSIDE instead — see MANTRA_MANIFEST/modules/termux-app.md §11, which draws
the line between an artefact downloaded by hand (number at both ends of the
filename, versioning.md) and one fetched by name (filename frozen, version
inside).

THREE PLACES, AND ALL THREE MUST MATCH — versioning.md §3, and its measured
trap: TTT_MINI carried build 127 in every document while the phone's app list
said 1.0, and the number the person can SEE is the worst of the three to lose.

    tools/build_installer.py   VERSION   -> the `edition: v<n>` line
    server.py                  APP_VERSION
    the banner                 drawn from APP_VERSION, so it follows

The installer is regenerated at the end, so the edition line can never be
bumped without the file it names being rebuilt.
"""

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILDER = os.path.join(ROOT, "tools", "build_installer.py")
SERVER = os.path.join(ROOT, "server.py")


def read(p):
    return open(p, encoding="utf-8").read()


def main():
    b = read(BUILDER)
    m = re.search(r'^VERSION = "(\d+)"', b, re.M)
    if not m:
        sys.exit("could not find VERSION in build_installer.py")
    old = int(m.group(1))

    s = read(SERVER)
    ms = re.search(r'^APP_VERSION = "v(\d+)"', s, re.M)
    if not ms:
        sys.exit("could not find APP_VERSION in server.py")
    if int(ms.group(1)) != old:
        sys.exit("they already disagree: installer v%d, server v%s. "
                 "Fix that by hand first." % (old, ms.group(1)))

    new = int(sys.argv[1]) if len(sys.argv) > 1 else old + 1
    if new <= old and len(sys.argv) == 1:
        sys.exit("v%d is not higher than v%d" % (new, old))

    open(BUILDER, "w", encoding="utf-8").write(
        re.sub(r'^VERSION = "\d+"', 'VERSION = "%d"' % new, b, count=1,
               flags=re.M))
    open(SERVER, "w", encoding="utf-8").write(
        re.sub(r'^APP_VERSION = "v\d+"', 'APP_VERSION = "v%d"' % new, s,
               count=1, flags=re.M))

    print("v%d -> v%d" % (old, new))
    subprocess.run([sys.executable, BUILDER], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
