"""Minutes-since-midnight helpers. Everything shown to the user is 12-hour AM/PM."""


def hm(t):
    h, m = map(int, t.split(":"))
    return h * 60 + m


def fmt24(mins):
    """'09:30' (for .ics files and ids)."""
    return f"{mins // 60:02d}:{mins % 60:02d}"


def fmt(mins):
    """'9:30 AM' (everything you read)."""
    h, m = divmod(mins, 60)
    return f"{(h - 1) % 12 + 1}:{m:02d} {'AM' if h < 12 or h == 24 else 'PM'}"


def t12(hhmm):
    """'13:15' -> '1:15 PM'; '' stays ''."""
    return fmt(hm(hhmm)) if hhmm else ""


def span12(span):
    """'08:00-08:15' -> '8:00 AM-8:15 AM'."""
    return "-".join(t12(x) for x in span.split("-")) if span else ""


def overlaps(a, b):
    return a["day"] == b["day"] and a["s"] < b["e"] and b["s"] < a["e"]
