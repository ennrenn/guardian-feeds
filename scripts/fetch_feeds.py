#!/usr/bin/env python3
"""Fetch every RSS feed listed in feeds.txt and merge the items into one CSV.

Writes three files to the output folder (default: site/):
  guardian_feeds.csv  one row per article, with duplicates across feeds merged
  articles.json       the same rows without descriptions, for the preview page
  status.json         what happened to each feed, for the status panel

Uses only the Python standard library, so there is nothing to install.
"""

import argparse
import csv
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
USER_AGENT = "Mozilla/5.0 (compatible; feed-collector/1.0)"
TIMEOUT = 30          # seconds per request
ATTEMPTS = 3          # tries per feed before giving up
WORKERS = 2           # feeds fetched at once; kept low so the Guardian does not rate-limit us
INCLUDE_DESCRIPTION = True   # set to False to leave article summaries out

NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "media": "http://search.yahoo.com/mrss/",
}

COLUMNS = [
    "title", "link", "published", "author", "categories", "description",
    "image_url", "source_feeds", "feed_count", "guid",
]


def read_feeds(path):
    """Read feed URLs, one per line. Blank lines and lines starting # are skipped."""
    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and line not in urls:
            urls.append(line)
    return urls


def fetch(url):
    """Return (bytes, None) on success or (None, message) on failure."""
    last = "unknown error"
    for attempt in range(1, ATTEMPTS + 1):
        wait = 2 * attempt  # seconds to pause before the next try
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read(), None
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code not in (429, 500, 502, 503, 504):
                break  # 403, 404 and the like will not improve on a retry
            if e.code == 429:
                # "Too many requests": wait as long as the server asks, else back off.
                try:
                    wait = min(int(e.headers.get("Retry-After", "")), 60)
                except ValueError:
                    wait = 15 * attempt
        except OSError as e:  # includes URLError, timeouts and dropped connections
            last = str(getattr(e, "reason", e))
        if attempt < ATTEMPTS:
            time.sleep(wait)
    return None, last


def clean(text):
    """Strip HTML tags, decode entities and collapse whitespace."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def to_iso(value):
    """Turn an RSS date (RFC 822) or ISO date into UTC ISO 8601, or '' if unreadable."""
    value = (value or "").strip()
    if not value:
        return ""
    try:
        moment = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return ""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def child_text(element, tag):
    found = element.find(tag, NS)
    return (found.text or "").strip() if found is not None else ""


def best_image(item):
    """Pick the widest media:content or media:thumbnail image, else an enclosure."""
    best_url, best_width = "", -1
    for node in item.findall("media:content", NS) + item.findall("media:thumbnail", NS):
        url = node.get("url", "")
        try:
            width = int(node.get("width", 0))
        except ValueError:
            width = 0
        if url and width > best_width:
            best_url, best_width = url, width
    if not best_url:
        enclosure = item.find("enclosure")
        if enclosure is not None:
            best_url = enclosure.get("url", "")
    return best_url


def parse_feed(data):
    """Return (feed title, list of item dicts) from RSS 2.0 bytes."""
    root = ET.fromstring(data)
    channel = root.find("channel")
    if channel is None:
        raise ValueError("no <channel> element, so this is not an RSS feed")
    items = []
    for node in channel.findall("item"):
        link = child_text(node, "link")
        guid = child_text(node, "guid")
        if not (link or guid):
            continue
        items.append({
            "title": clean(child_text(node, "title")),
            "link": link,
            "guid": guid or link,
            "published": to_iso(child_text(node, "pubDate")) or to_iso(child_text(node, "dc:date")),
            "author": "; ".join(e.text.strip() for e in node.findall("dc:creator", NS) if e.text),
            "categories": [e.text.strip() for e in node.findall("category") if e.text],
            # The Guardian ends every summary with a "Continue reading..." link; drop it.
            "description": re.sub(r"\s*Continue reading\.\.\.$", "", clean(child_text(node, "description"))),
            "image_url": best_image(node),
        })
    return clean(child_text(channel, "title")), items


def process(url):
    data, error = fetch(url)
    if error:
        return {"url": url, "title": "", "items": [], "error": error}
    try:
        title, items = parse_feed(data)
    except (ET.ParseError, ValueError) as e:
        return {"url": url, "title": "", "items": [], "error": f"could not read as RSS: {e}"}
    return {"url": url, "title": title, "items": items, "error": ""}


def feed_name(url):
    """Short label for a feed, e.g. 'education/higher-education'."""
    path = urlparse(url).path.strip("/")
    if path.endswith("/rss"):
        path = path[:-4]
    elif path == "rss":
        path = ""
    return path or url


def merge(results):
    """Combine items from all feeds into one row per article."""
    rows, seen = [], {}
    total = 0
    for result in results:
        if result["error"]:
            continue
        name = feed_name(result["url"])
        for item in result["items"]:
            total += 1
            row = seen.get(item["guid"])
            if row is None:
                row = {**item, "categories": list(dict.fromkeys(item["categories"])), "feeds": [name]}
                seen[item["guid"]] = row
                rows.append(row)
            else:
                if name not in row["feeds"]:
                    row["feeds"].append(name)
                for cat in item["categories"]:
                    if cat not in row["categories"]:
                        row["categories"].append(cat)
    rows.sort(key=lambda r: r["published"], reverse=True)
    return rows, total


def flatten(row):
    return {
        "title": row["title"],
        "link": row["link"],
        "published": row["published"],
        "author": row["author"],
        "categories": " | ".join(row["categories"]),
        "description": row["description"] if INCLUDE_DESCRIPTION else "",
        "image_url": row["image_url"],
        "source_feeds": " | ".join(row["feeds"]),
        "feed_count": len(row["feeds"]),
        "guid": row["guid"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--feeds", type=Path, default=ROOT / "feeds.txt", help="file listing feed URLs")
    parser.add_argument("--out", type=Path, default=ROOT / "site", help="output folder")
    args = parser.parse_args()

    urls = read_feeds(args.feeds)
    if not urls:
        sys.exit(f"No feed URLs found in {args.feeds}")

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(process, urls))

    # Feeds that were rate-limited get one more go, one at a time, after a pause.
    limited = [i for i, r in enumerate(results) if r["error"] == "HTTP 429"]
    if limited:
        print(f"{len(limited)} feed(s) were rate-limited; waiting 30 seconds, then trying again.")
        time.sleep(30)
        for i in limited:
            results[i] = process(urls[i])
            time.sleep(3)

    rows, total = merge(results)
    flat = [flatten(r) for r in rows]

    args.out.mkdir(parents=True, exist_ok=True)
    # utf-8-sig adds a byte order mark so Excel reads accents and symbols correctly.
    with open(args.out / "guardian_feeds.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(flat)

    preview_cols = ["title", "link", "published", "author", "categories", "feed_count"]
    with open(args.out / "articles.json", "w", encoding="utf-8") as f:
        json.dump([{k: r[k] for k in preview_cols} for r in flat], f, ensure_ascii=False)

    failures = [{"url": r["url"], "error": r["error"]} for r in results if r["error"]]
    status = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": os.environ.get("GITHUB_REPOSITORY", ""),
        "feeds_total": len(urls),
        "feeds_ok": len(urls) - len(failures),
        "items_total": total,
        "items_unique": len(rows),
        "failures": failures,
        "feeds": [{"url": r["url"], "title": r["title"], "items": len(r["items"]), "error": r["error"]}
                  for r in results],
    }
    with open(args.out / "status.json", "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

    print(f"{status['feeds_ok']} of {status['feeds_total']} feeds fetched; "
          f"{status['items_unique']} unique articles ({total} before merging duplicates).")
    for fail in failures:
        print(f"  FAILED {fail['url']}: {fail['error']}")
    print(f"CSV saved to: {(args.out / 'guardian_feeds.csv').resolve()}")

    if status["feeds_ok"] == 0:
        sys.exit("No feeds could be fetched, so nothing will be published.")


if __name__ == "__main__":
    main()
