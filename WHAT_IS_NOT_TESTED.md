# What is not tested — TOML v4

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

## Opened in a browser once, on 25.8.2026

Baba ran v3 on the phone at 04:58 and photographed it. That is the first time any of this was
seen. It found a real fault immediately: **the picker overlay was translucent** — `rgba(11,13,16,
.97)` — and the whole page printed through behind the folder list. It is the page's own solid
background now.

The rest of the page below is still only inspected in code.

## Otherwise never opened in a browser

**Almost no human eye has seen this page.** This is the exact failure that put five faults in front of
Baba at 03:20 on 25.8.2026: three versions shipped through nine gates without anyone opening a
browser. Named here so it is not claimed by silence.

Unproven: the layout at 390px, the 44px targets, the masked text wrapping in the textarea, the
picker being usable with a thumb, the amber against the near-black on a real phone screen at
brightness, and whether the whole thing survives 250% text size.

`navigator.clipboard.writeText` is untested. It requires a secure context; `http://127.0.0.1`
counts as one in Chrome and Safari, but that is read from the specification, not measured here.
The fallback — select the text so it can be copied by hand — is also untested.

## The updater now works against real GitHub — measured

The repository was made public on 25.8.2026, on Baba's word. Measured immediately after, with no
credential anywhere: the raw installer returns 200, the anonymous install runs, and a `toml-update`
against real GitHub took a faked v1 install to v3 and the version on disk changed.

**What is still not proven is that path from a phone**, on mobile data, through whatever proxy a
Croatian carrier puts in the way.

**Before it went public, the full history was scanned** — every blob in every commit, by known key
prefixes and by deny-by-default. It found Baba's real TTT-LLL usernames in a test fixture. That
door has no password behind the username, so the name is the whole credential. They were replaced
with invented ones and **the history was rewritten and force-pushed before the repository was ever
public.** GitHub's own copy was then re-cloned and re-scanned: zero.

The earlier clone command given on 25.8.2026 could not have worked while the repo was private —
raw 404, clone page 404, measured.

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
- 22 checks on the picker root: that Downloads is where it opens, that its symlink resolves and
  is allowed, and that a link inside Downloads pointing out of every root is still refused —
  three mutations, including comparing the path as a string before resolving it
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
