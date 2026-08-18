# Raw Ingestion Summary (Phase 0 input)

Fetched 2026-08-17. This is **raw source data only** — nothing here is a graph entity/relationship yet.
This satisfies the "RAW SOURCES" step of the ingestion pipeline in `CHANDLEROS_BLUEPRINT.md` (Knowledge Ingestion section).
Next step is manual curation: turning these into `entities` / `relationships` / `evidence` rows per the schema in
Section 8 of the blueprint.

## GitHub — `github/`
Source: public GitHub REST API, user `Harshithvarma007`, no auth (60 req/hr limit was enough for this pull).
- `repos.json` — raw API response, 15 repositories.
- `repos_enriched.json` — same repos + per-repo language breakdown + README content pulled in.
- `readmes/*.md` — full README text for the 10 repos that have one.

Repos without a README (ChatPDF, Amazon-dashboard, Datasets, Tennis-Analysis, PES2UG21CS312_Jenkins) will need either
a manual description or a `git clone` + code inspection to extract anything beyond name/language/topics.

## Kaggle — `kaggle/`
Source: official Kaggle API (`kaggle` Python package), authenticated with the credential in `kaggle.json`
(root of project — gitignored, never commit it).
- `kernels.json` — 100 notebooks/kernels (capped by the API at 100 results even with `--page-size 200` —
  pagination via `--page-token` would be needed to get older ones beyond the 100 if you have more).
- `datasets.json` — 25 datasets published.
- `profile_page_raw.html` — mostly useless; Kaggle's profile page is a JS-rendered SPA, so this is just the shell.
  The structured `kernels.json`/`datasets.json` are the actually useful Kaggle sources.

Many kernels are Kaggle Learn course exercises (e.g. "Exercise: Missing Values", "Exercise: Random Forests") —
these are learning artifacts, not portfolio projects, and should probably be excluded or tagged separately
during curation rather than treated as `Project` entities.

## Medium — `medium/`
Source: local Medium data export (official "Download your data" feature — `medium/README.html` confirms this),
parsed from the raw HTML in `../../medium/posts/`. No network calls.
- `posts_parsed.json` — 71 items, each with `date`, `title`, plain-text `text`, `char_count`.
- `profile.json` — profile bio text.

**Important**: most of the 71 items are short reply/comment threads ("Thank you", "Great read!!") from engaging
with other people's posts, not original articles — `char_count` is the useful filter. Roughly the top 20 by
`char_count` (see below) are real original blog posts worth turning into Vector RAG chunks (Section 10) and,
where they describe a project, graph entities. The rest are noise for knowledge-base purposes, though they could
still matter for a "writing style" signal if ever relevant.

### Real articles (char_count > 4000, i.e. actual posts not replies)
1. 📝LLM Text Detection (2024-07-11)
2. Building an LLM from Scratch (2025-09-23)
3. 🎧 Spotify Dashboard: Advanced Power BI Project🎧 (2024-07-16)
4. End To End Machine Learning Project – Part I (2024-06-25)
5. ChatPdf: End to End Gen AI Project (2024-08-13)
6. End-To-End ML Project: Spam Classification 🚀 (2024-07-15)
7. Gradient Descent from Scratch (2026-04-19)
8. End To End Machine Learning Project – Part II (2024-07-02)
9. An AI's 'Brain' Isn't One Thing (2025-11-12)
10. I Analyzed 141,000 Data Jobs (2025-07-18)
11. Building an AI Product From Scratch: Why Detox? (2026-07-29)
12. How I built an AI to Read Batsmen (2025-10-21)
13. The Serial Killer: Why I Trust Data Over Intuition (2026-01-21)
14. The Village That Learned to Think (2025-11-01)
15. Why Are Lawyers Risking Their Careers for AI? (2025-11-12)
16. SQL on LeetCode retrospective (2025-10-26)
17. The $5 Trillion Moment (2025-10-31)
18. How AI Sees the World (2025-10-30)
19. Polymath (2025-03-03)
20. 10 Mistakes I Made While Learning ML (2025-10-27)

(Full list with exact char counts in `medium/posts_parsed.json`, sorted arbitrarily by filename — sort by
`char_count` descending to reproduce this list.)

## What's NOT covered yet
- **LinkedIn** — explicitly skipped per your instruction; add later via LinkedIn's own data export if wanted.
- **Resume** — not yet located; if you have a resume file, point me at it and it becomes another source.
- **Portfolio website content** — `harshithvarma.in` is listed as your GitHub blog URL; not yet crawled.
- **Book / research content** (referenced in `plan.md` and present in `Desktop/Master Rag - 0 to 1/`) — not yet pulled in.

## Cross-source overlaps worth noting during curation
Several projects appear in more than one source and should resolve to the **same** `Project` entity with
multiple evidence rows, not duplicate entities:
- LLM Text Detection: GitHub repo `LLM_Text_Detection` + Kaggle kernel + Kaggle dataset + Medium post.
- Spam Email Classification: GitHub repo `Spam-email`/`Sapm-mail-Deployment` + Kaggle kernel + Medium post.
- Spotify Dashboard: GitHub repo `Spotify-Dashboard` + Medium post.
- ChatPDF: GitHub repo `ChatPDF` + Medium post.
- Trace The Ace: multiple Kaggle kernels + a Kaggle dataset (no GitHub repo seen yet).
