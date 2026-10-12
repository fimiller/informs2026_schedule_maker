"""Name and affiliation matching (accent/case folding, nicknames, acronyms like MIT)."""

import re
import unicodedata

_TRANS = str.maketrans({"ı": "i", "ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "đ": "d", "Đ": "D",
                        "ß": "ss", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "þ": "th"})

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "phd", "md"}

NICKNAMES = [
    {"dan", "daniel", "danny"}, {"tom", "thomas", "tommy"}, {"gabe", "gabriel"},
    {"jeff", "jeffrey", "jeffery"}, {"andrew", "andy", "drew"}, {"geri", "geraldine"},
    {"thiago", "tiago"}, {"mike", "michael"}, {"bob", "rob", "robert", "bobby"},
    {"bill", "will", "william", "billy"}, {"jim", "jimmy", "james"}, {"joe", "joseph"},
    {"chris", "christopher"}, {"matt", "matthew"}, {"nick", "nicholas", "nicolas"},
    {"alex", "alexander", "alejandro"}, {"sam", "samuel"}, {"ben", "benjamin"},
    {"dave", "david"}, {"steve", "steven", "stephen"}, {"tony", "anthony"},
    {"kate", "katherine", "catherine", "kathy", "katie"}, {"liz", "elizabeth", "beth"},
    {"jen", "jenn", "jennifer"}, {"pat", "patrick", "patricia"}, {"ed", "edward", "eddie"},
    {"rick", "richard", "rich"}, {"greg", "gregory"}, {"ted", "theodore"}, {"vince", "vincent"},
]

_ALIASES = {}
for group in NICKNAMES:
    for n in group:
        _ALIASES.setdefault(n, set()).update(group)


def fold(s):
    s = unicodedata.normalize("NFKD", (s or "").translate(_TRANS))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def tokens(name):
    s = fold(name).replace("'", "").replace("’", "")
    s = re.sub(r"[()\[\]\"]", " ", s)
    return [t for t in re.split(r"[\s\-.,]+", s) if t and t not in SUFFIXES]


def aliases(first):
    return _ALIASES.get(first, {first})


def match_name(query, cand):
    """Return (quality, reason) or None. quality: 'strong' | 'loose'."""
    q, c = tokens(query), tokens(cand)
    if len(q) < 2 or len(c) < 2:
        return None
    qf, ql, qsur = q[0], q[-1], q[1:]
    words = [t for t in c if len(t) > 1]
    if c[-1] == ql and all(p in c[1:] for p in qsur):
        if words and words[0] == qf:
            return "strong", ""
        if words and words[0] in aliases(qf):
            return "strong", f"nickname: listed as {cand}"
        if len(c[0]) == 1 and c[0] == qf[0]:
            return "loose", f"first initial only: {cand}"
        if qf in words[1:-1] or aliases(qf) & set(words[1:-1]):
            return "loose", f"goes by middle name? {cand}"
        return None
    if words and words[0] in aliases(qf) and ql in c[1:-1]:
        return "loose", f"compound surname: {cand}"
    return None

AFF_STOP = {"university", "of", "the", "at", "and", "institute", "school", "college", "dept",
            "department", "inc", "llc", "de", "la", "del", "di", "du", "und", "for", "in",
            "universidad", "universite", "universitat", "universita", "center", "centre"}

AFF_ALIASES = [  # applied to folded text before tokenizing
    (r"\buc\b", "university of california"), (r"\bpenn state\b", "pennsylvania state"),
    (r"\bgatech\b", "georgia technology"), (r"\btech\b", "technology"),
    (r"\but\b", "university of texas"),
]

ACRONYM_SKIP = {"of", "the", "and", "at", "for", "in", "de"}


def aff_tokens(a):
    s = fold(a)
    for pat, rep in AFF_ALIASES:
        s = re.sub(pat, rep, s)
    return {t for t in re.split(r"[^a-z0-9]+", s) if t and t not in AFF_STOP}


def acronym(a):
    words = [w for w in re.split(r"[^a-z0-9]+", fold(a)) if w and w not in ACRONYM_SKIP]
    return "".join(w[0] for w in words)


def same_aff(a, b):
    ta, tb = aff_tokens(a), aff_tokens(b)
    if not ta or not tb:
        return False
    # "MIT" vs "Massachusetts Institute of Technology", "CMU", "UCLA", "UIUC", ...
    for short, long_ in ((a, b), (b, a)):
        s = re.sub(r"[^a-z]", "", fold(short))
        if 2 <= len(s) <= 5 and " " not in fold(short).strip() and acronym(long_) in (s, s + "u", "u" + s):
            return True
    # Words that separate different institutions sharing a name (UPenn vs Penn State).
    if (ta ^ tb) & {"state", "technology", "polytechnic", "medical", "a", "m"}:
        return False
    return ta <= tb or tb <= ta or len(ta & tb) / len(ta | tb) >= 0.5


def cluster_affs(affs):
    clusters = []
    for a in affs:
        for cl in clusters:
            if same_aff(a, cl[0]):
                cl.append(a)
                break
        else:
            clusters.append([a])
    return clusters
