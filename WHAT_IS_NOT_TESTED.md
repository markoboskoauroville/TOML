# What is not tested — TOML v1

Per `four-tests.md` §"Say what you did NOT test", and it is as plain as what works.

## Never run on Termux

**Everything below was measured on Linux x86, not on Android.** The installer was run for real,
but with `#!/bin/bash` substituted for the Termux shebang and `$PREFIX` pointed at a temporary
folder. The following are therefore unproven:

- `pkg install python` / `pip install flask waitress` inside Termux
- `waitress` importing on Android — the code falls back to Flask's own server if it does not
- `$PREFIX/bin` being on the path, so that typing `toml` works
- whether Termux's `webbrowser.open` reaches Android's browser at all. If it does not, the URL
  is printed and can be opened by hand — that path is untested too

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

The upgrade test installs v1 over v1, because there is no v0. It proves files are replaced and
unrelated files survive; it does not prove a *format* change survives, because no format has
changed yet.

## What was measured

- 47 parser/merge checks, including Baba's real 21-account Hume export and real 5-key Groq export
- 24 checks against a real server over real HTTP: DNS rebinding, cross-site Origin, missing
  guard header, absolute paths, `..` climbs, symlink escape, empty file, prose, binary, and the
  same merge run twice
- three mutations, each confirmed to move behaviour and not only the file:
  the `[[ ]]` block-end fix, the parser pass order, the guard header check
- the installer run for real, and its output compared byte for byte against the repository
