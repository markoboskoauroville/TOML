"""TEST 1 and TEST 3 — the parser and the merge, alone.

    python3 tests/test_parse_merge.py

No Flask, no network, no key. Every case here is hand-written except the
ones marked REAL, which read Baba's actual exports if they are present
and skip cleanly if they are not.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import merge as M      # noqa: E402
import parsers         # noqa: E402

passed = failed = skipped = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ok   " + name)
    else:
        failed += 1
        print("  FAIL " + name + ("  — " + str(detail) if detail else ""))


def skip(name, why):
    global skipped
    skipped += 1
    print("  skip " + name + "  — " + why)


G = "gsk_" + "A" * 52
G2 = "gsk_" + "B" * 52
HUME_API = "H" * 48
HUME_SEC = "S" * 64

EXPORT = """av.live.vmix
API key
%s
Secret key
%s

cafeteria.media
API key
%s
Secret key
%s
""" % (HUME_API, HUME_SEC, "J" * 48, "T" * 64)

# ---------------------------------------------------------------- 1 --
print("1 THE LABEL PASS — Hume account pairs\n")
pairs, consumed = parsers.parse_pairs(EXPORT)
check("1a two accounts", len(pairs) == 2, len(pairs))
check("1b the name above the label becomes the account name",
      [p["name"] for p in pairs] == ["av.live.vmix", "cafeteria.media"],
      [p["name"] for p in pairs])
check("1c key and secret land the right way round",
      pairs[0]["key"] == HUME_API and pairs[0]["secret"] == HUME_SEC)
check("1d both halves are consumed, so pass 2 cannot re-take them",
      HUME_API in consumed and HUME_SEC in consumed)

print("\n1b THE UGLY CASES")
check("1e empty input", parsers.parse_pairs("")[0] == [])
check("1f a label with nothing under it is dropped, not crashed",
      parsers.parse_pairs("a\nAPI key\n")[0] == [])
check("1g a missing Secret key label drops that account",
      parsers.parse_pairs("a\nAPI key\nAAAA\n")[0] == [])
check("1h blank lines between label and value are tolerated",
      len(parsers.parse_pairs("a\nAPI key\n\n\n%s\nSecret key\n\n%s\n"
                              % (HUME_API, HUME_SEC))[0]) == 1)
check("1i case does not matter",
      len(parsers.parse_pairs("a\napi KEY\n%s\nSECRET Key\n%s\n"
                              % (HUME_API, HUME_SEC))[0]) == 1)
check("1j an account with no name still gets taken, named by position",
      parsers.parse_pairs("API key\n%s\nSecret key\n%s\n"
                          % (HUME_API, HUME_SEC))[0][0]["name"] == "account 1")
check("1k the same account twice is stored once",
      len(parsers.parse_pairs(EXPORT + EXPORT)[0]) == 2)

# ---------------------------------------------------------------- 2 --
print("\n2 THE SHAPE PASS — bare tokens\n")
s = parsers.parse_singles("%s\n%s\n" % (G, G2))
check("2a five-line groq export shape", s.get("groq") == [G, G2], s)
check("2b prose around the keys is ignored",
      parsers.parse_singles("my groq keys, for the app:\n%s\ncafeteria\n" % G)
      .get("groq") == [G], parsers.parse_singles("cafeteria\n%s\n" % G))
check("2c a 32-hex assemblyai key is NOT filed as speechify",
      parsers.parse_singles("a" * 32).get("assemblyai") == ["a" * 32])
check("2d sk-ant- is anthropic, not openai",
      "anthropic" in parsers.parse_singles("sk-ant-" + "x" * 30))
check("2e the same key twice is stored once",
      parsers.parse_singles("%s %s" % (G, G)).get("groq") == [G])

print("\n2b THE ORDER OF THE PASSES IS THE DESIGN")
_p, _c = parsers.parse_pairs(EXPORT)
after = parsers.parse_singles(EXPORT, _c)
flat = [k for v in after.values() for k in v]
check("2f no Hume key leaks into the shape pass as 'unknown'",
      HUME_API not in flat and HUME_SEC not in flat, after)

# ---------------------------------------------------------------- 3 --
print("\n3 THE MERGE — nothing that was in the file comes out of it\n")
# THE NAMES HERE ARE INVENTED, AND THAT IS NOT COSMETIC.
#
# TTT-LLL's door has no password behind the username — the name IS the
# whole credential. tests/live_check.py in that repo says so in its own
# words: "a real name in a committed test file is a credential in the
# repository." This file was drafted with Baba's real ADMIN_USER1 and
# FREE_USER1 in it, and it was caught on 25.8.2026 in the scan before
# making this repository public. A private repo is not a safe place to
# park a credential either; it is one setting away from being a public
# one.
#
# What the checks below actually need is a value that must SURVIVE the
# merge untouched, and any string does that.
BASE = '''# Baba's own note, which must survive
ADMIN_USER1  = "testuser"
FREE_USER1   = "otheruser"

GROQ_API_KEYS = [
    "%s",
]
''' % G

merged, rep = M.merge(BASE, pairs, {"groq": [G, G2]})
check("3a the comment survives", "# Baba's own note, which must survive" in merged)
check("3b ADMIN_USER1 survives with its value",
      'ADMIN_USER1  = "testuser"' in merged)
check("3c FREE_USER1 survives", 'FREE_USER1   = "otheruser"' in merged)
check("3d the new groq key was appended", G2 in merged)
check("3e the groq key already there was not duplicated",
      merged.count(G) == 1, merged.count(G))
check("3f it is reported as already there",
      rep["groq"] == {"added": 1, "skipped": 0, "already": 1, "names": []},
      rep["groq"])
check("3g both hume accounts were added", merged.count("[[HUME_ACCOUNTS]]") == 2)
check("3h the account name is carried through", 'name   = "av.live.vmix"' in merged)

print("\n3b IT PARSES, AND IT SAYS WHAT IT MEANT")
try:
    import tomllib
    d = tomllib.loads(merged)
    check("3i the merged text is valid TOML", True)
    check("3j groq array has both keys", d["GROQ_API_KEYS"] == [G, G2],
          d.get("GROQ_API_KEYS"))
    check("3k 2 hume accounts, each with name/key/secret",
          len(d["HUME_ACCOUNTS"]) == 2
          and sorted(d["HUME_ACCOUNTS"][0]) == ["key", "name", "secret"],
          d.get("HUME_ACCOUNTS"))
    check("3l the values survived intact",
          d["HUME_ACCOUNTS"][0]["key"] == HUME_API
          and d["HUME_ACCOUNTS"][0]["secret"] == HUME_SEC)
except ImportError:
    skip("3i-3l valid TOML", "no tomllib on this python")

print("\n3c IDEMPOTENT — merging twice is merging once")
twice, rep2 = M.merge(merged, pairs, {"groq": [G, G2]})
check("3m running it again changes nothing", twice == merged,
      "%d chars -> %d" % (len(merged), len(twice)))
check("3n and it says it added nothing",
      rep2["groq"]["added"] == 0 and rep2["hume"]["added"] == 0, rep2)

print("\n3d THE EMPTY AND THE ABSENT")
fresh, _ = M.merge("", pairs, {"groq": [G]})
check("3o no secrets file at all still produces a whole file",
      "GROQ_API_KEYS" in fresh and "[[HUME_ACCOUNTS]]" in fresh)
nothing, repn = M.merge(BASE, [], {})
check("3p an export with no keys leaves the file byte for byte",
      nothing == BASE, "%d -> %d" % (len(BASE), len(nothing)))
check("3q an unknown token is counted and NOT merged",
      M.merge(BASE, [], {"unknown": ["z" * 40]})[1]["unknown"]["skipped"] == 1)
check("3r the five-AssemblyAI-in-Speechify fault cannot happen here",
      "z" * 40 not in M.merge(BASE, [], {"unknown": ["z" * 40]})[0])

print("\n3e A KEY IS NEVER REMOVED")
gone, _ = M.merge(BASE, [], {"groq": []})
check("3s a key in the file but not in the export stays", G in gone)

print("\n3f THE MASK IS DENY-BY-DEFAULT")
m = M.mask(merged)
check("3t no full key is visible in the masked text",
      G not in m and HUME_API not in m and HUME_SEC not in m)
check("3u a short value like a username is left readable",
      "testuser" in m, m[:200])
check("3v an unknown key FORMAT is masked too — it is length, not shape",
      "Q" * 40 not in M.mask('X = "%s"' % ("Q" * 40)))

# ---------------------------------------------------------------- 4 --
print("\n4 REAL — Baba's actual exports, if they are here\n")
UP = "/mnt/user-data/uploads"
hume_f = os.path.join(UP, "Hume.txt")
groq_f = os.path.join(UP, "groq_api.txt")
if os.path.exists(hume_f):
    p, s2 = parsers.parse(open(hume_f, encoding="utf-8").read())
    check("4a the real Hume export gives 21 accounts", len(p) == 21, len(p))
    check("4b every one has a 48-char key and a 64-char secret",
          all(len(x["key"]) == 48 and len(x["secret"]) == 64 for x in p))
    check("4c nothing from it fell through to unknown",
          not s2.get("unknown"), len(s2.get("unknown", [])))
else:
    skip("4a-4c the real Hume export", "not in uploads")
if os.path.exists(groq_f):
    _p2, s3 = parsers.parse(open(groq_f, encoding="utf-8").read())
    check("4d the real Groq export gives 5 keys",
          len(s3.get("groq", [])) == 5, len(s3.get("groq", [])))
    check("4e and nothing else", list(s3) == ["groq"], list(s3))
else:
    skip("4d-4e the real Groq export", "not in uploads")

if os.path.exists(hume_f) and os.path.exists(groq_f):
    ph, sh = parsers.parse(open(hume_f, encoding="utf-8").read())
    _pg, sg = parsers.parse(open(groq_f, encoding="utf-8").read())
    both, repr_ = M.merge(BASE, ph, sg)
    check("4f both real files merge into one file",
          repr_["hume"]["added"] == 21 and repr_["groq"]["added"] == 5, repr_)
    try:
        import tomllib
        dd = tomllib.loads(both)
        check("4g and the result is valid TOML with 21 accounts and 6 groq keys",
              len(dd["HUME_ACCOUNTS"]) == 21 and len(dd["GROQ_API_KEYS"]) == 6,
              (len(dd.get("HUME_ACCOUNTS", [])), len(dd.get("GROQ_API_KEYS", []))))
        check("4h no real key is visible in the masked view",
              not any(a["key"] in M.mask(both) for a in dd["HUME_ACCOUNTS"]))
    except ImportError:
        skip("4g-4h", "no tomllib")

print("\n{} passed, {} failed, {} skipped".format(passed, failed, skipped))
sys.exit(1 if failed else 0)
