# What is not tested — TOML v2

Per `four-tests.md` §"Say what you did NOT test", and it is as plain as what works.

## Never run on Termux

**Everything below was measured on Linux x86, not on Android.** The installer was run for real,
but with `#!/bin/bash` substituted for the Termux shebang and `$PREFIX` pointed at a temporary
folder. The following are therefore unproven:

- `pkg install python` / `pip install flask waitress` inside Termux
- `waitress` importing on Android — the code falls back to Flask's own server if it does not
- `$PREFIX/bin` being on the path, so that typing `toml` works
- **`am start` against a real Chrome.** The whole Chrome branch is driven by an injected fake.
  Its logic is checked, including the exit-zero lie; what is unproven is that a real Android
  `am` behaves the way `ma-reader-thermux` recorded it behaving. The four package names are
  copied from there and not re-verified
- `termux-open-url` reaching a real Android browser. A stand-in on the PATH proves the server
  calls it with the right URL and nothing more

## Never opened in a browser

**No human eye has seen this page.** This is the exact failure that put five faults in front of
Baba at 03:20 on 25.8.2026: three versions shipped through nine gates without anyone opening a
browser. Named here so it is not claimed by silence.

Unproven: the layout at 390px, the 44px targets, the masked text wrapping in the textarea, the
picker being usable with a thumb, the amber against the near-black on a real phone screen at
brightness, and whether the whole thing survives 250% text size.

`navigator.clipboard.writeText` is untested. It requires a secure context; `http://127.0.0.1`
counts as one in Chrome and Safari, but that is read from the specification, not measured here.
The fallback — select the text so it can be copied by hand — is also untested.

## Tested with substitutes

The upgrade test is now real: **v1 is cloned from GitHub, installed, used, and v2 installed on
top of it.** v1's absence of `opener.py` is asserted before the upgrade, so it cannot be the new
version installed twice. What it still does not prove is a *format* change surviving, because
no stored format has changed.

## What was measured

- 47 parser/merge checks, including Baba's real 21-account Hume export and real 5-key Groq export
- 17 checks on the auto-open: every branch of the chooser, the `am` exit-zero lie, the wait for
  the port, port collision, and one end-to-end run where the real server opens a real URL that
  really answers 200 on a port it had to move to
- 24 checks against a real server over real HTTP: DNS rebinding, cross-site Origin, missing
  guard header, absolute paths, `..` climbs, symlink escape, empty file, prose, binary, and the
  same merge run twice
- three mutations, each confirmed to move behaviour and not only the file:
  the `[[ ]]` block-end fix, the parser pass order, the guard header check, trusting `am`'s exit
  code, opening on a timer, and opening the wanted port rather than the bound one
- the installer run for real, and its output compared byte for byte against the repository
