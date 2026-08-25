# TOML

**Merge an exported key file into a secrets file, on your own phone, and copy the result.**

Termux · Flask · loopback only · version 3

---

## What it is for

21 Hume accounts, each an API key *and* a secret key. 5 Groq keys, and more every rotation.
Streamlit wants them as TOML. Typing that into a phone by hand is not a thing anybody does
twice, and pasting keys into a chat to have them formatted puts them in a transcript that
cannot be unsent.

So the formatting happens on the device that already has the keys.

    1  choose your secrets file      (or none, to start a fresh one)
    2  choose the exported key file
    3  press merge, press copy, paste into Streamlit

## Install

```bash
curl -fsSL -O https://raw.githubusercontent.com/markoboskoauroville/TOML/main/toml-termux.sh && bash toml-termux.sh
```

Then `toml`, from anywhere. **The page opens by itself — there is no address to type.**

## Update

```bash
toml-update
```

One word, every time. It fetches the current version, **asks before it changes anything**, and
installs it in the same run — because an updater that only leaves a command behind and installs
nothing *looks exactly like nothing happening*.

**Four checks before it replaces a single file**, each able to fail on its own:

| | catches |
|---|---|
| size | a captive-portal login page instead of an installer |
| shebang on line 1 | an error page, an HTML redirect |
| `bash -n` with **no output at all** | a genuine parse warning |
| the last line is `# TOML-INSTALLER-END` | a transfer that stopped early |

**The last one is there because `bash -n` is not a completeness check.** Measured 25.8.2026: this
installer cut in half mid-heredoc makes `bash -n` print `warning: here-document delimited by
end-of-file` and **exit zero**. It passed the parse check and installed half the app.
`ma-reader-thermux/update.sh` uses the same three checks and has the same hole.

If any check fails it prints **nothing was changed** and stops. That sentence is the point of the
checks.

### The filename is frozen, on purpose

`toml-termux.sh`, and it will not be renamed. `toml-update` fetches it by that exact name, so a
new number in the filename every build would break the one command you actually type. The version
lives in the `edition: v<n>` line inside the file, in `APP_VERSION`, and in the banner —
`tools/bump.py` keeps all three in step and refuses to run when they already disagree. See
`MANTRA_MANIFEST/modules/termux-app.md` §11 for why this and `versioning.md` are both right.

### How it opens, and why it is not one line

`webbrowser.open` does not work on Termux. It looks for desktop browsers and desktop
environment variables, finds none, and returns False silently. That was v1's bug.

    1  Chrome by intent    am start -a VIEW -d <url> -p <package>
    2  the phone default   termux-open-url
    3  a desktop           xdg-open, open
    4  webbrowser          last, and only as a courtesy

**`am start` prints its failures and still exits zero.** Asking for a package that is not
installed writes `Error: Activity not started` and returns success, so the *output* is read,
not the status. Filtered by package rather than activity, because Chrome's activity name has
changed between versions and the package name never has. Both lessons are from
`ma-reader-thermux`.

**It waits for the port to really accept a connection before opening.** v1 opened on a
one-second timer, which is a guess about how long a phone takes to bind a socket. Guess low and
the page says "connection refused", and somebody who sees that closes the tab and does not try
again.

### It never fails to start because a port is busy

8099, then the next fifteen, then whatever the system gives — and it **says which**, because a
page that quietly opens somewhere other than where you expect is its own confusion. The thing
most likely to be holding 8099 is this app still running from before, so without this it would
block on its own success case.

## What it does not do

**It does not write anything.** The merged text lives in the server process and goes when you
quit it. Not saved, not cached, not logged.

**It does not talk to the network.** There is no outbound call in the program. Grep it.

**It does not remove a key.** A key in your file but not in the export stays. Rotating means
adding the new one here and revoking the old one at the provider — a merge tool that dropped
keys would be doing the revoking in the wrong place, with no way back.

**It does not lose your file.** Comments, usernames, `SHEETS_URL`, spacing: through byte for
byte. The merge is surgical — only the arrays and the `[[HUME_ACCOUNTS]]` blocks are touched.

## Security

Loopback only — `127.0.0.1`, **not** `0.0.0.0`. The transcription app binds every interface so
any device on the Wi-Fi can reach it; that is right for a transcription page and wrong for a
keyring. A café network is a room full of strangers.

Binding to loopback stops the network. It does not stop a **web page**: any site open in
another tab can make your browser send requests to `127.0.0.1:8099` in the background. Three
checks, lifted from `GDRIVE_DOWNLOADER_FLASK_MACOS/localguard.py`:

| | |
|---|---|
| **Host** | must be a loopback name — stops DNS rebinding, which binding alone does not catch |
| **Origin** | if present, must be this app |
| **Header** | a header the page always sends and a cross-site request cannot set |

Files are read only from inside your home directory, **resolved through symlinks before the
check**, so a link pointing at `/etc` does not get you `/etc`.

Values are masked on screen. Copy takes the real text either way — you never have to reveal to
copy. The mask is deny-by-default: every quoted value over 12 characters is blanked, whatever
its format, so a key shape nobody has seen yet is masked too.

## The parsers

**Two passes, and the order is the design.**

Pass 1 reads **labels** — Hume's export has an account name, `API key`, the key, `Secret key`,
the secret. Both halves are plain alphanumeric with no prefix, so shape cannot tell them apart.

Pass 2 reads **shape**, skipping everything pass 1 consumed: `gsk_`, `sk-ant-`, `AIza`/`AQ.`,
`sk_`, 32-hex, and a loose catch-all that lands in `unknown` and is **never** merged into a
named provider without being asked. That last part is deliberate: TTT-LLL's `import_keys` has a
generic fallback that put five AssemblyAI keys in the Speechify ring.

## Tests

```bash
python3 tests/test_parse_merge.py    # 47 — parser, merge, masking, the real exports
python3 tests/test_server.py         # 24 — real HTTP, guard sabotage, path escapes
python3 tests/test_opener.py         # 17 — auto-open, the am lie, port collision
python3 tests/test_update.py         # 30 — toml-update, over a real HTTP server
python3 tools/build_installer.py --check
```

The installer is **generated** from the source files, never pasted beside them, and carries the
hash of each source it was built from. One repository, not two copies.

*Mantra Productions.*
