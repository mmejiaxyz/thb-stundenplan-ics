# THB Stundenplan → iCalendar

Crawls the [TH Brandenburg Stundenplan](https://informatik.th-brandenburg.de/studium/plaene-und-termine/stundenplan/)
pages and publishes each schedule as an `.ics` file you can subscribe to in your phone's
calendar. The site's schedule ("sked campus") changes frequently — a GitHub Actions job
re-runs the crawler daily and re-publishes the files, so your calendar stays in sync.

## How it works

1. `crawl.py` fetches a schedule page (e.g. Interactive Media M.Sc., 1. Semester).
2. It extracts the embedded iframe URL (which points to a generated HTML file under
   `fileadmin/stundenplan/…`).
3. It parses every week's table into events: date, start/end time, course, lecturers,
   room and notes. Because events differ week to week (parallel courses, shifting days,
   holidays), each occurrence becomes its own `VEVENT`.
4. It writes `interactive-media-master-1-semester.ics` (one file per entry in
   `SEMESTERS`). Event UIDs are stable, so subscribed calendars update/remove changed
   events on refresh.

## Local run

```bash
python3 crawl.py
```

Requires only the Python standard library. It writes `*.ics` files into the repo root.

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
   https://<you>.github.io/<repo>/interactive-media-master-1-semester.ics
   ```
4. Subscribe in your calendar app:
   - **Google Calendar (web/Android):** Settings → Add calendar → From URL → paste the
     `.ics` URL. Refreshes automatically a few times a day.
   - **Apple Calendar (iPhone/iPad):** Settings → Calendar → Accounts → Add Account →
     Other → Add Subscribed Calendar → paste the URL. Refreshes via the app's update
     interval.

## Schedules

Each entry in `SEMESTERS` (in `crawl.py`) is a `{stem, url, courses}` dict and produces
its own `.ics`:

| File | Source | Courses included |
|---|---|---|
| `interactive-media-master-1-semester.ics` | Interactive Media M.Sc., 1. Sem | Motion graphics, Creative technologies, Media theories, Interactive products and services, Projekt 1 |
| `informatik-bachelor-1-semester-1-gruppe.ics` | Informatik B.Sc., 1. Sem, Gruppe 1 | Einführung in die praktische Informatik (V + Ü) |

## Filtering to your enrolled courses

`courses` entries are matched case-insensitively as substrings of the course title
(e.g. `projekt 1`, not just `projekt`, so the elective *Fortgeschrittenes
Projektmanagement* stays out; `einführung in die praktische informatik` matches both
the *V* and *Ü* forms). Edit the lists to match your registration and commit.

## Notes

- Times are converted to UTC; DST (CEST/CET) is handled automatically.
- The crawler tolerates the iframe URL changing between semesters because it always
  resolves it from the page first.
- If the site layout changes structurally, the workflow run will fail loudly — check
  the Actions log and adjust the parser.