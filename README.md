# Guardian feeds to CSV

This repository fetches a list of RSS feeds (mainly the Guardian's, plus any other site you add), merges the articles into one CSV, and publishes the CSV on a GitHub Pages site. A GitHub Action does the fetching, so the work happens on GitHub's servers when you press a button.

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

## Adding a feed from another site

Add its URL to `feeds.txt` on a new line and run the workflow again. Any standard RSS feed works. The script reads the usual fields (title, link, date, author, categories, summary and image), copes with the different ways sites present them, and removes the stock endings some sites add to every summary, such as "Continue reading..." or "was published on FE News by...". The `source` column shows which site each article came from, and the site's page has a filter box that searches it.

A site you add might need a small tweak if its summaries are laid out unusually. If a feed fails or looks wrong, the status panel on the page names it and gives the reason.

## Limiting the CSV by date

By default the CSV holds the last five days of articles. The window moves with the day you run the workflow: a run on 14 October keeps everything published from 9 October (00:00 UTC) onwards, and a run on 3 November keeps everything from 29 October onwards. Nothing needs changing as the months pass. The site's summary line says which date the CSV starts from and how many older items were left out. Articles with no publication date are kept.

Near the top of `scripts/fetch_feeds.py` there are two settings. `MAX_AGE_DAYS = 5` is the rolling window; change the number to widen or narrow it, or set it to `None` to switch it off. `START_DATE` is a fixed day, written as `"2026-10-01"`, that never moves; it is empty by default, and if you set both, the later cut-off applies. To change a setting, open the file in GitHub, choose the pencil icon, edit the line, commit, and run the workflow again. To try a different window on your own computer without editing the file, add `--max-age-days 10` to the command, or `--from-date 2026-10-01`, or `--max-age-days 0 --from-date ""` for no limit.

## What is in the CSV

There is one row per article. The same article often appears in several feeds, so it is merged into one row, with `source_feeds` listing every feed it appeared in and `feed_count` giving the number. The columns are title, link, source (the website, such as theguardian.com or fenews.co.uk), published (UTC), author, categories, description (plain text), image_url, source_feeds, feed_count and guid. Rows are sorted newest first. The file is saved so Excel shows accents and symbols correctly.

Each feed only holds its most recent items (about 20 for the Guardian, 50 for FE News), so every run gives a snapshot of what is in the feeds at that moment. It does not build up a history. For busy feeds that is a few days, so an article from early in the month may already be gone from the feed by the time you run it. The date filter only removes articles; it cannot bring back ones a feed has dropped.

## Things to know

Pages sites are public, even when the repository is private, unless your GitHub plan includes private Pages. The CSV contains article summaries from the sites you fetch. If you would rather not publish them, set `INCLUDE_DESCRIPTION = False` near the top of `scripts/fetch_feeds.py`.

If a feed fails, the run carries on with the rest and the site lists the failures with the reason. The run only stops, and leaves the previous site in place, if no feed could be fetched at all.
