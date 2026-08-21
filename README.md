# Smartphone Recommendation via Aspect-Based Sentiment Analysis

Research backend implementing the methodology: scrape smartphone details, prices and
customer reviews with **Playwright**, run an **aspect-based sentiment analysis (ABSA)**
pipeline over the reviews, aggregate per-aspect scores into a feature score database,
and serve a weighted **recommendation engine** through a **FastAPI** API.

```
Reviews ─▶ Step 1 Preprocess ─▶ Step 2 Segment ─▶ Step 3 Aspect extraction
                                                        │
                                                        ▼
Recommendation ◀─ Feature scores ◀─ Step 6 Aggregate ◀─ Step 4 Sentiment
       engine        (output layer)                      classification
```

---

## 1. Quick start (real Hugging Face corpus — no demo data)

**Recommended path:** build the corpus in Google Colab (fast download), then import locally.

### A) Google Colab

1. Open [`notebooks/Amazon_Reviews_2023_ABSA_Corpus.ipynb`](notebooks/Amazon_Reviews_2023_ABSA_Corpus.ipynb) in Colab  
   (or upload it from this repo).
2. Run all cells. It pulls exact reviews from
   [`McAuley-Lab/Amazon-Reviews-2023`](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023),
   filters real smartphones, applies **methodology Step 1** preprocessing, and downloads `hf_corpus.zip`.

### B) On your PC

```powershell
cd "d:\4TH YEAR\RESEARCH SETUP\smartphone recommendation"
pip install -r requirements.txt

# unzip hf_corpus.zip into .\hf_corpus\  (phones.jsonl + reviews.jsonl + manifest.json)

python run.py reset-corpus --yes
python run.py import-corpus .\hf_corpus --replace --analyze
python run.py serve
# -> http://127.0.0.1:8000/ui/
```

`reset-corpus` removes demo/sample/old rows. `import-corpus --analyze` runs methodology
Steps 2–6 (segment → aspect extraction → sentiment → structured rows → aspect scores).

### Alternative: stream HF directly on your PC (slower)

```powershell
python run.py reset-corpus --yes
python scripts/build_hf_corpus.py --max-phones 40 --max-reviews 100 --min-ratings 500 --max-review-scan 2000000 --out data/exports/hf_corpus
python run.py import-corpus data/exports/hf_corpus --replace --analyze
```

Or one-shot into the DB: `python run.py ingest-hf ...` (same data source, less portable).

---

## Methodology mapping

| Step | What | Where |
|---|---|---|
| 1 | Dedupe, spam/empty, HTML, normalise, language filter | Colab / `build_hf_corpus.py` |
| 2 | Sentence segmentation | `import-corpus --analyze` |
| 3–4 | Aspect extraction + sentiment (lexicon or LLM) | same |
| 5 | Structured aspect–sentiment dataset | SQLite `aspect_sentiments` |
| 6 | Aspect score aggregation → feature table | SQLite `aspect_scores` |
| — | Weighted recommendation | `/ui/` Recommend page |

Aspects: **battery, camera, display, performance, price**.

---

## Old quick start notes

```bash
# optional live scrape (CLI only, not the website)
python run.py login
python run.py scrape -q "samsung galaxy s24"
```

`seed-demo` is **test scaffolding only — never report it**. Prefer `reset-corpus` + HF import.

---

## 1b. The dashboard

Everything the CLI can do is also driveable from a browser. The UI lives in
`app/static/` and is served by the API itself at `/ui/`, so there is nothing to
build or install — it is plain HTML, CSS and JavaScript with no dependencies and
no CDN calls, and it works offline.

| View | What it is for |
|---|---|
| Dashboard | Corpus counts, sentiment and aspect distributions, the full phone × aspect score matrix as a colour-coded heatmap, and the star-rating validation report. |
| Phones | Every handset with its aspect scores. Click one for a radar chart, the positive/neutral/negative split per aspect, parsed specifications, price history, and the individual sentences behind each score. |
| Recommend | Weight sliders per aspect plus affordability, with presets and price/review filters. Each result shows its weighted contribution breakdown, evidence coverage, and strengths and weaknesses. |
| Corpus | Browse reviews and expand any one to see it segmented into sentences with the aspects and sentiment extracted from each — Steps 2 to 4 applied to a single review. |
| Scrape | Build a collection run from search terms and product IDs, then watch it progress live. |
| Pipeline | Run the ABSA stages, choose the engine, or re-aggregate scores after changing weighting settings. |
| Jobs | History of scrape and analysis runs with their result payloads. |

To check the UI still renders after a change, with the server running:

```bash
python tests/_ui_smoke.py http://127.0.0.1:8000
```

It drives every view in a real browser, fails on any console error or failed
request, and writes screenshots to `tests/_ui_shots/`.

---

## 2. Pipeline stages and where they live

| Step | Description | Module |
|---|---|---|
| Input | Search, product specs, price, reviews | `app/scrapers/amazon.py` |
| 1 | Clean, normalise, spam + language filter, de-duplicate | `app/nlp/preprocess.py` |
| 2 | Sentence segmentation | `app/nlp/segment.py` |
| 3 + 4 | Aspect extraction and sentiment classification | `app/nlp/absa.py` |
| 5 | Structured aspect–sentiment records | `aspect_sentiments` table |
| 6 | Aspect score aggregation | `app/nlp/aggregate.py` |
| Output | Feature score database | `GET /features` |
| — | Recommendation engine | `app/services/recommender.py` |

Aspects (`ASPECT_SET=core`): **battery, camera, display, performance, price**.
`ASPECT_SET=extended` adds design, software, connectivity, audio, durability.

---

## 3. The two ABSA engines

| Engine | Requires | Use |
|---|---|---|
| `llm` | `LLM_API_KEY` | The annotator described in the methodology |
| `lexicon` | nothing | Offline rule-based **baseline** for comparison |

`ABSA_ENGINE=auto` (the default) picks `llm` when an API key is present, otherwise
`lexicon`. Having both matters for the dissertation: the lexicon engine gives you a
baseline to argue the LLM against, rather than reporting LLM numbers with nothing to
compare them to.

The LLM engine works with any OpenAI-compatible endpoint:

```ini
# OpenAI
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini

# Local Ollama (free, no data leaves your machine)
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=llama3.1:8b
```

Steps 3 and 4 are issued as **one batched call** per group of sentences rather than
two separate calls. That is faster, cheaper, and removes the inconsistency that
appears when a second call has to re-read an aspect it did not extract itself. If a
batch fails after all retries, it degrades to the lexicon engine and the rows are
marked `method="lexicon_fallback"` so the fallback is visible in your data.

---

## 4. Score definitions

**Step 6 aggregation**, per (phone, aspect):

```
raw_score = (positive + 0.5 × neutral) / mentions            ∈ [0, 1]
```

The stored `score` additionally applies Bayesian shrinkage toward the corpus mean:

```
score = (mentions × raw_score + k × corpus_mean) / (mentions + k)
```

with `k = SHRINKAGE_STRENGTH` (default 5). A phone with 400 battery mentions keeps
its own score almost unchanged; a phone with 2 mentions is pulled toward the average.
Without this, one lucky review tops the ranking. Both values are stored, so you can
report raw scores and use shrunk scores for ranking.

**Recommendation:**

```
final = Σ(wₐ × scoreₐ) / Σ(wₐ)
```

Missing aspects are imputed with the candidate-set mean and flagged `imputed`, never
scored as 0 — scoring a never-mentioned camera as zero would punish a phone for
sparse reviews rather than for a bad camera. Each result reports `coverage`, the
share of requested weight backed by real mentions.

**Price is handled as two separate signals**, because they answer different questions:

- `price` aspect — what reviewers *say* about value for money (from reviews)
- `affordability` — the numeric price min-max normalised across the corpus, 1 = cheapest

Weight either or both in `POST /recommend`.

---

## 5. Scraping notes

**Reviews behind sign-in.** Amazon gates the full paginated review list behind a
signed-in session in most locales. Run once:

```bash
python run.py login
```

A real browser window opens; sign in manually, then press Enter. Cookies are saved to
`data/storage_state.json` and reused. Without it the scraper still collects the
reviews embedded on each product page and logs a warning.

**Politeness and blocking.** Randomised delays (`MIN_DELAY_S`/`MAX_DELAY_S`), retries
with exponential backoff, static assets blocked, and explicit CAPTCHA detection that
raises a clear error instead of silently writing an empty dataset. If you get blocked:
raise the delays, set `HEADLESS=false`, or set `BROWSER_CHANNEL=chrome` to use your
installed Chrome.

**Debugging selectors.** When a page fails to parse, a screenshot and the HTML are
written to `data/artifacts/` so you can diagnose it without re-running the scrape.

**Ethics and terms of service.** Automated scraping may conflict with a site's terms
of use, and research ethics rules at your institution may apply to collecting
user-generated content. Confirm what your supervisor and ethics board require before
running large collections, keep volumes modest, and consider citing an existing public
review dataset as a robustness check. Reviews contain personal data; the reviewer name
is stored, so exclude it from anything you publish.

---

## 6. API

Interactive docs at `/docs`. Scraping and analysis return a job id immediately;
poll `GET /jobs/{job_id}`.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/scrape` | Scrape phones, prices, reviews (background job) |
| `POST` | `/analyze` | Run Steps 1–6 (background job) |
| `POST` | `/analyze/recompute-scores` | Re-aggregate only, after changing weights |
| `GET` | `/features` | Feature score database (output layer) |
| `GET` | `/phones` | List phones, with filters |
| `GET` | `/phones/{id}` | Specs, price history, aspect scores |
| `GET` | `/phones/{id}/opinions` | **Evidence**: the sentences behind each label |
| `GET` | `/reviews` | Browse the corpus |
| `GET` | `/reviews/{id}/sentences` | Steps 2–4 for one review |
| `POST` | `/recommend` | Ranked recommendations with per-aspect breakdown |
| `GET` | `/stats` | Corpus statistics for the dataset description |
| `GET` | `/validation` | Star-rating agreement check |
| `POST` | `/export` | CSVs of every stage |
| `GET` | `/jobs/{id}` | Job progress |

Example scrape:

```bash
curl -X POST http://127.0.0.1:8000/scrape -H "Content-Type: application/json" -d '{
  "queries": ["samsung galaxy s24", "google pixel 8"],
  "max_phones_per_query": 3,
  "max_reviews_per_phone": 150,
  "analyze_after_scrape": true
}'
```

Example recommendation:

```bash
curl -X POST http://127.0.0.1:8000/recommend -H "Content-Type: application/json" -d '{
  "weights": {"camera": 0.4, "battery": 0.3, "performance": 0.2, "affordability": 0.1},
  "budget_max": 900,
  "min_reviews": 20,
  "top_k": 5
}'
```

---

## 7. Validation and reporting

`GET /validation` compares each review's star rating with the polarity of the aspects
extracted from that same review. The rating is an independent human signal the pipeline
never sees, so agreement is evidence the ABSA step behaves sensibly. It is a **weak,
review-level label** against **aspect-level** predictions, so perfect agreement is
neither expected nor desirable — treat it as a check for systematic polarity bias, not
as accuracy.

For a defensible accuracy figure you still need a **manually annotated gold set**.
The recommended route:

1. `POST /export`, then sample 300–500 rows from `sentences.csv`.
2. Have two annotators label aspect + sentiment independently.
3. Report inter-annotator agreement (Cohen's κ).
4. Score both engines against the gold set: precision, recall, macro-F1.
5. Report the LLM against the lexicon baseline.

`GET /stats` gives the numbers for the dataset section: review counts, exclusion
breakdown by reason, sentence and aspect counts, and the sentiment distribution.

---

## 8. Project layout

```
app/
  core/        config, logging, database session
  models/      SQLAlchemy tables + Pydantic schemas
  scrapers/    base.py (browser), parsers.py (pure parsing), amazon.py, pipeline.py
  nlp/         aspects.py, preprocess.py, segment.py, prompts.py, absa.py, aggregate.py
  services/    jobs.py, analysis.py, recommender.py, exports.py, demo.py
  api/routes/  scrape, analysis, phones, reviews, recommend, jobs
  static/      dashboard: index.html, app.css, app.js (no build step)
  main.py      FastAPI app
run.py         CLI
tests/         test_parsers.py (offline fixtures), _ui_smoke.py (browser check)
data/          SQLite database, exports/, artifacts/, storage_state.json
```

Tables: `smartphones`, `price_observations`, `reviews`, `sentences`,
`aspect_sentiments`, `aspect_scores`, `jobs`.

Reviews are **flagged, not deleted**, when filtered out (`excluded_reason`), so you can
report exact exclusion counts. Raw review text is kept alongside the cleaned version,
which keeps the dataset auditable.

---

## 9. Configuration reference

All settings live in `.env`; see `.env.example` for the annotated list. The ones that
change results:

| Variable | Default | Effect |
|---|---|---|
| `ASPECT_SET` | `core` | `core` (5 aspects) or `extended` (10) |
| `ABSA_ENGINE` | `auto` | `llm`, `lexicon`, or auto-select |
| `NEUTRAL_WEIGHT` | `0.5` | Neutral contribution to a score |
| `SHRINKAGE_STRENGTH` | `5.0` | Pull of sparse aspects toward the mean |
| `MIN_MENTIONS_FOR_SCORE` | `3` | Below this, an aspect is low-confidence |
| `LANGUAGE_FILTER` | `en` | Drop reviews in other languages |
| `MIN_DELAY_S` / `MAX_DELAY_S` | `1.5` / `4.0` | Scraping politeness delay |

After changing `NEUTRAL_WEIGHT` or `SHRINKAGE_STRENGTH`, run
`POST /analyze/recompute-scores` — no re-annotation needed.

---

## 10. Known limitations

State these in your dissertation rather than letting a reviewer find them:

- **Single source.** Amazon reviews skew toward buyers who chose the product, and
  scraped review sets are not random samples of opinion.
- **Selector fragility.** Marketplace HTML changes without notice; fallback selector
  tuples reduce breakage but cannot eliminate it.
- **LLM non-determinism.** Temperature is 0, but providers do not guarantee identical
  output across runs or model versions. Record `LLM_MODEL` and the date of every run.
- **Aspect coverage is uneven.** Reviewers discuss cameras far more than durability,
  so sparse aspects carry wide uncertainty. `mention_count` and `confidence` are stored
  per score for exactly this reason.
- **Price aspect conflates two things** — sticker price and perceived value. They are
  deliberately split into `price` and `affordability`.
- **English only** by default.
