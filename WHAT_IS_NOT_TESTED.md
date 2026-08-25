# What is not tested — TOML v3

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

## The updater cannot do its real job yet

**TOML is a private repository, so an anonymous download 404s.** `toml-update` is tested against a
real HTTP server on loopback and works perfectly there — but pointed at GitHub today it will reach
its "could not download it" branch every time. That branch is tested; the successful GitHub path
is not, and cannot be until the repository is public or a credential is put on the phone.

This also means the clone command given on 25.8.2026 —
`git clone https://github.com/markoboskoauroville/TOML.git` — **cannot have worked.** Confirmed by
measurement: raw 404, clone page 404.

## Tested with substitutes

The launchers carry Termux's shebang, so the tests invoke them through `bash` rather than
executing them. Check 1f asserts the shebang is the Termux one, so that substitution cannot
quietly become "the test runs a different program than the phone does".

The upgrade test is now real: **v1 is cloned from GitHub, installed, used, and v2 installed on
top of it.** v1's absence of `opener.py` is asserted before the upgrade, so it cannot be the new
version installed twice. What it still does not prove is a *format* change surviving, because
no stored format has changed.

## What was measured

- 47 parser/merge checks, including Baba's real 21-account Hume export and real 5-key Groq export
- 30 checks on `toml-update` against a real HTTP server: it installs a different version and the
  files on disk are asserted to have changed, all four validations, the y/n prompt, an unreachable
  host, and the frozen filename. Two mutations prove the warnings check and the sentinel check
  each fail alone — the first draft of them overlapped and one could be deleted with everything
  still green
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
