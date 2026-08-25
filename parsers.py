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
