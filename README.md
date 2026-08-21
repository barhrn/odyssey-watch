# Odyssey IMAX watch

Notifies via Telegram when **new IMAX screenings of "The Odyssey"** open at
**Planet Rishon LeZion** on a **Thursday or Friday** with room for 3 people.

Runs on GitHub Actions every 15 minutes — no server, no laptop left open.
**The repo must be public**: public repos get unlimited free Actions minutes,
while a private one would exhaust the Free plan's 2,000 min/month in ~20 days.

## Setup

1. **Create a Telegram bot**
   - Open Telegram, message [@BotFather](https://t.me/BotFather), send `/newbot`,
     follow the prompts. It replies with a token like `123456:ABC-DEF...`.
   - Send any message to your new bot (a bot cannot message you first).
   - Get your chat id: open
     `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser and copy
     `result[0].message.chat.id`.

2. **Push this folder to a GitHub repo**

   ```sh
   git init && git add -A && git commit -m "odyssey watch"
   gh repo create odyssey-watch --public --source=. --push
   ```

3. **Add the secrets**

   ```sh
   gh secret set TG_BOT_TOKEN   # paste the BotFather token
   gh secret set TG_CHAT_ID     # paste your chat id
   ```

4. **Test it** — Actions tab → "Odyssey IMAX watch" → *Run workflow*.
   You should get a Telegram message listing the screenings currently open.

## Local use

```sh
python3 odyssey_watch.py --list    # show current matches, no alerts
python3 odyssey_watch.py           # check + notify on new ones
python3 odyssey_watch.py --reset   # forget history, re-alert on everything
```

## Tuning

All at the top of `odyssey_watch.py`:

| setting | meaning |
|---|---|
| `CINEMAS` | `["1072"]` = Rishon LeZion. `None` = all sites. Others: 1025 Ayalon, 1070 Haifa, 1073 Jerusalem, 1074 Beer Sheva, 1075 Zichron Yaakov |
| `WEEKDAYS` | `{3, 4}` = Thu, Fri (Mon=0) |
| `SEATS_WANTED` | 3 |
| `REQUIRED_ATTR` | `"imax"`, or `None` to allow any format |

## Notes

- `odyssey_state.json` tracks which screenings you have already been told about,
  and the workflow commits it back so you are not re-alerted every 15 minutes.
- Seat counts are **estimates**. The API exposes only `availabilityRatio` (the
  fraction of the hall still free), never the seat map — that endpoint is behind
  bot protection. `ASSUMED_CAPACITY` converts the ratio to a rough seat count,
  and it cannot tell whether free seats are *adjacent*.
- Public repos have **unlimited free** Actions minutes on standard runners.
  Secrets stay encrypted and are not exposed by making the repo public.
- GitHub disables scheduled workflows in *public* repos after 60 days with no
  repository activity. If alerts go quiet, hit *Run workflow* once to re-arm.
- Cron runs are best-effort and get delayed when GitHub is busy, so the schedule
  avoids the top of the hour. Do not count on catching a drop that sells out in
  under a minute.
