#!/usr/bin/env python3
"""Crawler for TH Brandenburg schedule (sked campus) -> iCalendar (.ics).

Fetches a Stundenplan page, extracts the embedded sked HTML schedule
(iframe src), parses every week's table into events, and writes one
.ics file per semester. Cell ids from sked are reused as stable UIDs so
subscribed phone calendars can update/remove events on re-runs.
"""

import html.parser
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta

BASE = "https://informatik.th-brandenburg.de"

# Each semester has its own list of enrolled courses. Only matching events
# end up in that semester's .ics. Terms are matched case-insensitively as
# substrings of the course title (e.g. "projekt 1" so the elective
# "Fortgeschrittenes Projektmanagement" stays out).
SEMESTERS = [
    {
        "stem": "interactive-media-master-1-semester",
        "url": BASE + "/studium/plaene-und-termine/stundenplan/interactive-media-master/1-semester/",
        "courses": [
            "motion graphics",
            "creative technologies",
            "media theories",
            "interactive products and services",
            "projekt 1",
        ],
    },
    {
        "stem": "informatik-bachelor-1-semester-1-gruppe",
        "url": BASE + "/studium/plaene-und-termine/stundenplan/informatik-bachelor/1-semester/1-gruppe/",
        "courses": [
            "einführung in die praktische informatik",
        ],
    },
]

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

ROOM_RE = re.compile(r"^[A-Za-z]\.\d")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def extract_iframe_src(page_html):
    for m in re.finditer(r"<iframe[^>]*src=\"([^\"]+)\"", page_html):
        src = m.group(1)
        if "fileadmin/stundenplan" in src:
            if src.startswith("/"):
                src = BASE + src
            return src
    raise RuntimeError("No schedule iframe found on page")


class Cell:
    __slots__ = ("cls", "rowspan", "colspan", "cell_id", "data", "spans", "cur_span")

    def __init__(self, cls, rowspan, colspan, cell_id):
        self.cls = cls
        self.rowspan = rowspan
        self.colspan = colspan
        self.cell_id = cell_id
        self.data = []
        self.spans = []
        self.cur_span = None

    @property
    def text(self):
        return "".join(self.data)


class WeekParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []  # list of week tables; each is a list of rows
        self.in_week = False
        self.cur_table = None
        self.cur_row = None
        self.cur_cell = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "div" and a.get("class") == "w1":
            self.in_week = True
        elif tag == "table" and self.in_week:
            self.cur_table = []
        elif tag == "tr" and self.cur_table is not None:
            self.cur_row = []
        elif tag == "td" and self.cur_row is not None:
            self.cur_cell = Cell(
                a.get("class", ""),
                int(a.get("rowspan", 1)),
                int(a.get("colspan", 1)),
                a.get("id", ""),
            )
        elif tag == "span" and self.cur_cell is not None:
            self.cur_cell.cur_span = []

    def handle_endtag(self, tag):
        if tag == "span" and self.cur_cell is not None and self.cur_cell.cur_span is not None:
            self.cur_cell.spans.append("".join(self.cur_cell.cur_span).strip())
            self.cur_cell.cur_span = None
        elif tag == "td" and self.cur_cell is not None:
            self.cur_row.append(self.cur_cell)
            self.cur_cell = None
        elif tag == "tr" and self.cur_row is not None:
            self.cur_table.append(self.cur_row)
            self.cur_row = None
        elif tag == "table" and self.cur_table is not None:
            self.tables.append(self.cur_table)
            self.cur_table = None

    def handle_startendtag(self, tag, attrs):
        if tag == "br" and self.cur_cell is not None:
            self.cur_cell.data.append("\n")

    def handle_data(self, data):
        if self.cur_cell is not None:
            if self.cur_cell.cur_span is not None:
                self.cur_cell.cur_span.append(data)
            else:
                self.cur_cell.data.append(data)


def build_grid(rows):
    """Expand rowspan/colspan into a grid[r][c] -> Cell (or None)."""
    grid = []
    pending = {}  # future row -> set of occupied cols
    for r, cells in enumerate(rows):
        grid.append([None] * 40)
        col = 0
        for cell in cells:
            while col < len(grid[r]) and grid[r][col] is not None:
                col += 1
            for i in range(cell.colspan):
                grid[r][col + i] = cell
            for rr in range(1, cell.rowspan):
                pending.setdefault(r + rr, set()).update(range(col, col + cell.colspan))
            col += cell.colspan
        for c in pending.get(r, ()):
            grid[r][c] = "occupied"
    return grid


DAY_RE = re.compile(r"^(Mo|Di|Mi|Do|Fr|Sa|So),\s*(\d{2})\.(\d{2})\.(\d{2})$")
TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*Uhr")


def parse_week(rows):
    grid = build_grid(rows)
    if not grid:
        return []

    header_row = next(
        (r for r, row in enumerate(grid) if any(
            c and isinstance(c, Cell) and c.cls == "t" for c in row
        )),
        None,
    )
    if header_row is None:
        return []

    day_by_col = {}
    for c, cell in enumerate(grid[header_row]):
        if isinstance(cell, Cell) and cell.cls == "t":
            m = DAY_RE.match(cell.text.strip())
            if m:
                d = date(2000 + int(m.group(4)), int(m.group(3)), int(m.group(2)))
                for i in range(cell.colspan):
                    day_by_col[c + i] = d

    events = []
    seen = set()
    for row in grid:
        for cell in row:
            if not isinstance(cell, Cell) or cell.cls != "v":
                continue
            if id(cell) in seen:
                continue
            seen.add(id(cell))
            col = next(
                (c for c, x in enumerate(row) if x is cell),
                None,
            )
            if col is None or col not in day_by_col:
                continue
            tm = TIME_RE.search(cell.text)
            if not tm:
                continue
            events.append(
                {
                    "date": day_by_col[col],
                    "start": (int(tm.group(1)), int(tm.group(2))),
                    "end": (int(tm.group(3)), int(tm.group(4))),
                    "id": cell.cell_id,
                    "text": cell.text,
                    "spans": cell.spans,
                }
            )
    return events


def parse_event(raw):
    lines = [ln.strip() for ln in raw["text"].split("\n")]
    lines = [ln for ln in lines if ln]
    if not lines:
        return None

    tm = TIME_RE.search(lines[0])
    title = lines[1] if len(lines) > 1 else lines[0]

    spans = [s for s in raw["spans"] if s]

    room = ""
    lecturers = []
    if spans:
        if ROOM_RE.match(spans[-1]):
            room = spans[-1]
            lecturers = spans[:-1]
        else:
            lecturers = spans

    span_lines = set(spans)
    notes = "\n".join(
        ln for ln in lines[2:] if ln not in span_lines and not re.fullmatch(r"[\s,]+", ln)
    ).strip()

    desc_parts = []
    if lecturers:
        desc_parts.append("Dozierende: " + ", ".join(lecturers))
    if notes:
        desc_parts.append(notes)
    description = "\n".join(desc_parts)

    return {
        "date": raw["date"],
        "start": tm.group(1).zfill(2) + ":" + tm.group(2),
        "end": tm.group(3).zfill(2) + ":" + tm.group(4),
        "summary": title,
        "location": room,
        "description": description,
        "uid": "%s-%s" % (raw["date"].isoformat(), raw["id"]),
    }


def last_sunday_of_month(year, month):
    d = date(year, month + 1, 1) if month < 12 else date(year + 1, 1, 1)
    d -= timedelta(days=1)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def is_cest(d):
    mar = last_sunday_of_month(d.year, 3)
    oct_ = last_sunday_of_month(d.year, 10)
    return mar <= d < oct_


def to_utc(d, hhmm, offset):
    h, m = map(int, hhmm.split(":"))
    local = datetime(d.year, d.month, d.day, h, m) - timedelta(hours=offset)
    return local


def ics_datetime(dt):
    return dt.strftime("%Y%m%dT%H%M%SZ")


def fold_line(line):
    """Fold a content line to <=75 octets per RFC 5545 (CRLF + space)."""
    if len(line.encode("utf-8")) <= 75:
        return line
    out = []
    while len(line.encode("utf-8")) > 75:
        # cut at 74 octets to leave room for the continuation space
        cut = 0
        size = 0
        for ch in line:
            size += len(ch.encode("utf-8"))
            if size > 74:
                break
            cut += 1
        out.append(line[:cut])
        line = line[cut:]
    out.append(line)
    return "\r\n ".join(out)


def build_ics(events):
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//thb-stundenplan-crawler//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:THB Stundenplan",
        "X-WR-TIMEZONE:Europe/Berlin",
    ]
    for e in events:
        off = 2 if is_cest(e["date"]) else 1
        dtstart = to_utc(e["date"], e["start"], off)
        dtend = to_utc(e["date"], e["end"], off)
        lines += [
            "BEGIN:VEVENT",
            "UID:%s@thb-stundenplan" % e["uid"],
            "DTSTAMP:%s" % ics_datetime(datetime.utcnow()),
            "DTSTART:%s" % ics_datetime(dtstart),
            "DTEND:%s" % ics_datetime(dtend),
            "SUMMARY:%s" % sanitize(e["summary"]),
        ]
        if e["location"]:
            lines.append("LOCATION:%s" % sanitize(e["location"]))
        if e["description"]:
            lines.append("DESCRIPTION:%s" % sanitize(e["description"]))
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold_line(ln) for ln in lines) + "\r\n"


def sanitize(text):
    text = text.replace("\n", "\\n").replace("\r", "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return text


def is_enrolled(title, courses):
    norm = re.sub(r"\s+", " ", title).lower()
    return any(course in norm for course in courses)


def main():
    for spec in SEMESTERS:
        stem, url, courses = spec["stem"], spec["url"], spec["courses"]
        page = fetch(url)
        iframe = extract_iframe_src(page)
        print("Schedule source:", iframe, file=sys.stderr)

        html_doc = fetch(iframe)
        parser = WeekParser()
        parser.feed(html_doc)
        parser.close()

        weeks = [t for t in parser.tables if t]

        events = []
        for rows in weeks:
            events.extend(parse_week(rows))

        events.sort(key=lambda e: (e["date"], e["start"]))
        parsed = [p for p in (parse_event(e) for e in events) if p]
        included = [e for e in parsed if is_enrolled(e["summary"], courses)]
        excluded = [e["summary"] for e in parsed if not is_enrolled(e["summary"], courses)]

        out = stem + ".ics"
        with open(out, "w", encoding="utf-8") as f:
            f.write(build_ics(included))
        print(
            "Wrote %s (%d of %d events, %d weeks) - excluded: %s"
            % (out, len(included), len(parsed), len(weeks), ", ".join(sorted(set(excluded))))
        )


if __name__ == "__main__":
    main()