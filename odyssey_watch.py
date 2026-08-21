#!/usr/bin/env python3
"""
Watch planetcinema.co.il for newly-opened IMAX screenings of "The Odyssey"
on Thursday or Friday with enough seats left.

Alerts once per screening (state kept in odyssey_state.json), so running it
on a schedule only pings you about genuinely new stuff.

Usage:
    python3 odyssey_watch.py              # check + notify on new matches
    python3 odyssey_watch.py --list       # show all current matches, no state change
    python3 odyssey_watch.py --reset      # forget what was already seen
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

# ---------------------------------------------------------------- config ----

API = "https://www.planetcinema.co.il/il/data-api-service/v1/quickbook/10100"

FILM_IDS = {"7460s2r", "7460s2r2"}      # "האודיסאה" (he) + russian-subbed print
FILM_NAME = "The Odyssey / האודיסאה"

# Cinemas to watch. None = all Planet sites. Ids: 1025 Ayalon, 1070 Haifa,
# 1072 Rishon LeZion, 1073 Jerusalem, 1074 Beer Sheva, 1075 Zichron Yaakov.
CINEMAS = ["1072"]                       # Rishon LeZion only

WEEKDAYS = {3, 4}                        # Mon=0 ... Thu=3, Fri=4
REQUIRED_ATTR = "imax"                   # set to None to drop the IMAX filter
SEATS_WANTED = 3

# availabilityRatio is the fraction of the hall still free. The API never says
# how big the hall is, so we approximate with a conservative IMAX capacity to
# turn that ratio into a seat count.
ASSUMED_CAPACITY = 300

DAYS_AHEAD = 90                          # how far out to ask for dates
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "odyssey_state.json")
HEBREW_DAYS = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
EN_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# ------------------------------------------------------------------ http ----


def get(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
            "Accept": "application/json",
            "Referer": "https://www.planetcinema.co.il/",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def cinemas():
    until = (date.today() + timedelta(days=DAYS_AHEAD)).isoformat()
    body = get(f"{API}/cinemas/with-event/until/{until}?attr=&lang=he_IL")["body"]
    return {c["id"]: c["displayName"] for c in body["cinemas"]}


def dates_for(cinema_id):
    until = (date.today() + timedelta(days=DAYS_AHEAD)).isoformat()
    body = get(f"{API}/dates/in-cinema/{cinema_id}/until/{until}?attr=&lang=he_IL")["body"]
    return body["dates"]


def events_for(cinema_id, day):
    body = get(f"{API}/film-events/in-cinema/{cinema_id}/at-date/{day}?attr=&lang=he_IL")["body"]
    return body["events"]


# ----------------------------------------------------------------- logic ----


def seats_left(event):
    return int(event.get("availabilityRatio", 0) * ASSUMED_CAPACITY)


def matches(event):
    if event["filmId"] not in FILM_IDS:
        return False
    if REQUIRED_ATTR and REQUIRED_ATTR not in event.get("attributeIds", []):
        return False
    when = datetime.fromisoformat(event["eventDateTime"])
    if when.weekday() not in WEEKDAYS:
        return False
    if when < datetime.now():
        return False
    if event.get("soldOut"):
        return False
    return seats_left(event) >= SEATS_WANTED


def scan(names):
    """Return matching screenings across every watched cinema and date."""
    found = []
    targets = CINEMAS or list(names)
    for cid in targets:
        try:
            days = dates_for(cid)
        except urllib.error.URLError as e:
            print(f"warn: dates for {cid} failed: {e}", file=sys.stderr)
            continue
        for day in days:
            if datetime.strptime(day, "%Y-%m-%d").weekday() not in WEEKDAYS:
                continue          # skip the fetch entirely for non Thu/Fri days
            try:
                evs = events_for(cid, day)
            except urllib.error.URLError as e:
                print(f"warn: events for {cid} {day} failed: {e}", file=sys.stderr)
                continue
            for ev in evs:
                if matches(ev):
                    ev["_cinema"] = names.get(cid, cid)
                    found.append(ev)
    found.sort(key=lambda e: (e["eventDateTime"], e["_cinema"]))
    return found


def describe(ev):
    when = datetime.fromisoformat(ev["eventDateTime"])
    dow = when.weekday()
    return (
        f"{EN_DAYS[dow]} ({HEBREW_DAYS[dow]}) {when:%d/%m} {when:%H:%M} · "
        f"{ev['_cinema']} · {ev.get('auditorium', '?')} · "
        f"~{seats_left(ev)} seats free ({ev.get('availabilityRatio', 0):.0%})"
    )


# ------------------------------------------------------------- notifying ----


def notify(title, message, url=None):
    """macOS banner + Telegram, if configured. Always echoes to stdout."""
    print(f"\n*** {title}\n{message}\n" + (f"{url}\n" if url else ""))

    body = message.replace('"', "'")
    script = (
        f'display notification "{body}" with title "{title}" sound name "Glass"'
    )
    try:
        subprocess.run(["osascript", "-e", script], check=False, timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass

    token, chat = os.environ.get("TG_BOT_TOKEN"), os.environ.get("TG_CHAT_ID")
    if token and chat:
        text = f"{title}\n{message}" + (f"\n{url}" if url else "")
        data = json.dumps({"chat_id": chat, "text": text}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=15).read()
        except urllib.error.URLError as e:
            print(f"warn: telegram send failed: {e}", file=sys.stderr)


# ------------------------------------------------------------------ state ----


def load_state():
    try:
        with open(STATE_FILE) as f:
            return set(json.load(f).get("seen", []))
    except (OSError, ValueError):
        return set()


def save_state(seen):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"seen": sorted(seen), "updated": datetime.now().isoformat()}, f, indent=1)
    os.replace(tmp, STATE_FILE)


# ------------------------------------------------------------------ main ----


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="print all matches, leave state alone")
    ap.add_argument("--reset", action="store_true", help="clear the seen-screenings state")
    args = ap.parse_args()

    if args.reset:
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
        print("state cleared")
        return 0

    names = cinemas()
    found = scan(names)

    if args.list:
        print(f"{len(found)} matching screening(s) right now:")
        for ev in found:
            print("  " + describe(ev))
        return 0

    seen = load_state()
    new = [ev for ev in found if ev["id"] not in seen]

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    if new:
        lines = [describe(ev) for ev in new]
        notify(
            f"🎬 {len(new)} new IMAX Odyssey screening(s)",
            "\n".join(lines),
            new[0].get("bookingLink"),
        )
    else:
        print(f"{stamp}  no new screenings ({len(found)} known match(es) still open)")

    # Keep only ids that are still live, so the state file does not grow forever.
    save_state({ev["id"] for ev in found})
    return 0


if __name__ == "__main__":
    sys.exit(main())
