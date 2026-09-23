# THB Stundenplan → iCalendar

Crawls the [TH Brandenburg Stundenplan](https://informatik.th-brandenburg.de/studium/plaene-und-termine/stundenplan/)
pages and publishes your enrolled courses as a single `.ics` file you can subscribe to
in your phone's calendar. The site's schedule ("sked campus") changes frequently — a
GitHub Actions job re-runs the crawler daily and re-publishes the file, so your
calendar stays in sync.

## How it works

1. `crawl.py` fetches each schedule page (see `SEMESTERS`) and extracts the embedded
   iframe URL (a generated HTML file under `fileadmin/stundenplan/…`).
2. It parses every week's table into events: date, start/end time, course, lecturers,
   room and notes. Because events differ week to week (parallel courses, shifting days,
   holidays), each occurrence becomes its own `VEVENT`.
3. Only enrolled courses (see `courses` per semester) are kept, and all events from all
   sources are merged into a single `stundenplan.ics`. Event UIDs are stable, so a
   subscribed calendar updates/removes changed events on refresh.

## Local run

```bash
python3 crawl.py
```

Requires only the Python standard library. It writes `stundenplan.ics` into the repo root.

## Schedules

Each entry in `SEMESTERS` (in `crawl.py`) is a `{stem, url, courses}` dict:

| Source | Courses included |
|---|---|
| Interactive Media M.Sc., 1. Sem | Motion graphics, Creative technologies, Media theories, Interactive products and services, Projekt 1 |
| Informatik B.Sc., 1. Sem, Gruppe 1 | Einführung in die praktische Informatik (V + Ü) |

## Filtering to your enrolled courses

`courses` entries are matched case-insensitively as substrings of the course title
(e.g. `projekt 1`, not just `projekt`, so the elective *Fortgeschrittenes
Projektmanagement* stays out; `einführung in die praktische informatik` matches both
the *V* and *Ü* forms). Edit the lists to match your registration and commit.

## Self-verification

Before writing `stundenplan.ics` the crawler verifies every day of the combined
schedule and **fails loudly (exit 1) if any check fails**:

- each course keeps a single weekday across the semester,
- no duplicate event UIDs,
- no two classes overlap in time on the same day,
- every event has `end > start`,
- each parsed day header matches the real calendar weekday.

It also prints a per-day report of every generated event. Because the daily GitHub
Actions run fails on violations, a week-day mapping regression surfaces in the run log
instead of silently producing a wrong calendar.

## Setup (GitHub Pages hosting)

1. Push this repo to GitHub:
   ```bash
   git init -b main
   git add -A
   git commit -m "Initial commit"
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```
2. Enable Pages: **Settings → Pages → Build and deployment → Source: Deploy from a
   branch → main / (root) → Save**.
3. After the first scheduled run (or a `workflow_dispatch`), the file is live at:
   ```
   https://<you>.github.io/<repo>/stundenplan.ics
   ```
4. Subscribe in your calendar app:
   - **Google Calendar (web/Android):** Settings → Add calendar → From URL → paste the
     `.ics` URL. Refreshes automatically a few times a day.
   - **Apple Calendar (iPhone/iPad):** Settings → Calendar → Accounts → Add Account →
     Other → Add Subscribed Calendar → paste the URL. Refreshes via the app's update
     interval.

## Notes

- Times are converted to UTC; DST (CEST/CET) is handled automatically.
- The crawler tolerates the iframe URL changing between semesters because it always
  resolves it from the page first.
- If the site layout changes structurally, the workflow run will fail loudly — check
  the Actions log and adjust the parser.