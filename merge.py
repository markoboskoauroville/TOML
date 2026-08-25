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
