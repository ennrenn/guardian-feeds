# Guardian feeds to CSV

This repository fetches a list of Guardian RSS feeds, merges the articles into one CSV, and publishes the CSV on a GitHub Pages site. A GitHub Action does the fetching, so the work happens on GitHub's servers when you press a button.

## Setting it up

Create a new repository on GitHub and upload everything in this folder, keeping the folder structure (including the hidden `.github` folder). Replace the example in `feeds.txt` with your full list, one URL per line.

In the repository, go to Settings, then Pages, and set the source to GitHub Actions. Then open the Actions tab, choose Fetch feeds, and press Run workflow. After a minute or so the site is live at `https://YOUR-USERNAME.github.io/REPOSITORY-NAME/`. It shows how many feeds worked, lists any that failed, previews the articles, and has a Download CSV button. The Run again button on that page takes you back to the Actions tab.

To refresh on a timetable as well, open `.github/workflows/fetch-feeds.yml` and remove the `#` from the two schedule lines.

## Running it on your own computer

You need Python 3.9 or later and nothing else.

```
python scripts/fetch_feeds.py
```

The CSV appears in the `site` folder, as `site/guardian_feeds.csv`, and the last line the script prints gives the full path. This is also the fallback if GitHub's servers are ever refused by the Guardian but your own connection is not.

The Guardian sometimes answers "HTTP 429", which means too many requests. The script fetches two feeds at a time, waits as long as the Guardian asks, and tries any rate-limited feeds again after a 30 second pause.

## What is in the CSV

There is one row per article. The same article often appears in several feeds, so it is merged into one row, with `source_feeds` listing every feed it appeared in and `feed_count` giving the number. The columns are title, link, published (UTC), author, categories, description (plain text), image_url, source_feeds, feed_count and guid. Rows are sorted newest first. The file is saved so Excel shows accents and symbols correctly.

Each feed only holds its most recent items, so every run gives a snapshot of what is in the feeds at that moment. It does not build up a history.

## Things to know

Pages sites are public, even when the repository is private, unless your GitHub plan includes private Pages. The CSV contains article summaries from the Guardian. If you would rather not publish them, set `INCLUDE_DESCRIPTION = False` near the top of `scripts/fetch_feeds.py`.

If a feed fails, the run carries on with the rest and the site lists the failures with the reason. The run only stops, and leaves the previous site in place, if no feed could be fetched at all.
