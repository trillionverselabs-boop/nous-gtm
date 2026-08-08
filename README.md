# Nous GTM — Signal Discovery Dashboard

A public-signal intelligence dashboard for Nous Research GTM strategy. Pulls live developer signal from Hacker News, GitHub, HuggingFace, and Reddit — not claimed Nous metrics.

## What This Shows

| Section | Data Source | Status |
| --- | --- | --- |
| **Conversion Funnel** | Stage structure only | Method (not numbers) |
| **Pain Point Clusters** | HN, GitHub, HF, Reddit APIs | Real — sourced, clickable |
| **Competitor Friction** | Same public signal | Real — mention counts |

**Honesty:** Pain clusters and competitor friction are real, pulled from public developer signal. The conversion funnel shows stage structure and what I'd instrument — not claimed numbers. Frequency scores are a heuristic (`50 + avg(signal_strength) × 40`), not a claimed metric. No access to Nous internal usage data or enterprise customer records.

## Live

https://nous.trillionverselabs.com/prototype

## Architecture

```
nous-gtm/
├── app.py                    # Flask app — serves the /prototype route
├── run_prototype.py          # Signal collection pipeline
├── signal_discovery.db       # SQLite — raw signals from public APIs (gitignored)
├── output/
│   ├── clustered_pain_points.json     # Clustered pain points (regenerated)
│   └── competitor_friction.json       # Competitor mention counts (regenerated)
├── templates/
│   ├── base.html            # Shared layout (no nav/menu in public repo)
│   └── prototype.html       # Dashboard: funnel | clusters | friction
├── static/
│   ├── css/styles.css       # Design system (TVL tokens)
│   ├── js/accordion.js      # Click-to-drill interaction
│   └── robots.txt           # noindex, nofollow
├── Dockerfile
├── .env.example             # GITHUB_TOKEN, HF_TOKEN
├── .gitignore
└── scripts/
    └── verify.sh            # Verification checklist
```

## The Pipeline — How Signals Flow

The dashboard page at `/prototype` intentionally shows results only, not the pipeline that produces them. The full pipeline implementation is below — the actual code, not a stylized summary.

### Stage 1: Signal Collection

`run_prototype.py` hits four public sources on-demand:

| Source | Method | Auth | What it captures |
| --- | --- | --- | --- |
| Hacker News | Algolia Search API (`hn.algolia.com`) | None | Stories mentioning "hermes", "nous", "open weights" |
| GitHub | REST API (`/repos/NousResearch/issues`) | `GITHUB_TOKEN` | Issues, discussions, bug reports |
| HuggingFace | API (`/api/models/NousResearch`) | `HF_TOKEN` | Community discussions on model pages |
| Reddit | RSS feed (`r/LocalLLaMA`, `r/MachineLearning`) | None | Posts mentioning Hermes/open weights |

Each signal record stores: `source`, `platform_id`, `timestamp`, `raw_text`, `url`, `signal_strength` (0.3–1.0), `competitors` (JSON array of mentioned competitors).

### Stage 2: Ingest (`store_signal()`)

Raw records are inserted into `signal_discovery.db` (SQLite, local). Schema:

```sql
CREATE TABLE signals (
    id INTEGER PRIMARY KEY,
    source TEXT,
    timestamp TEXT,
    raw_text TEXT,
    url TEXT,
    signal_strength REAL,
    competitors TEXT
);
```

The database is excluded from the repo via `.gitignore` — it is local-only and regenerated on each run.

### Stage 3: Cluster & Score (`cluster_signals()` → `_heuristic_cluster()`)

Signals are grouped into pain-point clusters by keyword matching (`_CLUSTER_KEYWORDS` dict in `run_prototype.py`). Each cluster gets:

- **count** — number of signals matched by keyword (from `SELECT` filtered rows)
- **signal_frequency_score** — heuristic: `50 + avg(signal_strength) × 40`, range 50–90
- **tier** — `High` (count ≥ 40), `Medium` (count ≥ 10), `Low` (count < 10)
- **sources** — real source URLs with excerpts, linkable back to the original post

Results are written to `output/clustered_pain_points.json`.

### Stage 4: Rank & Route (`write_clusters()`)

Clusters are ranked by count (descending). Competitor friction is computed inline during clustering in `_heuristic_cluster()` — it iterates every signal and tallies which competitors are mentioned:

```python
comps = json.loads(competitors_raw)
for c in comps:
    competitor_friction[c] = competitor_friction.get(c, 0) + 1
```

Results written to `output/competitor_friction.json` — actual mention counts, not fabricated numbers.

## Running Locally

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Collect fresh signal (requires API tokens)
cp .env.example .env
# Edit .env with GITHUB_TOKEN and HF_TOKEN
python run_prototype.py

# 3. Serve the dashboard
python app.py
# → http://localhost:8050/prototype
```

**Requirements:** `.env` with `GITHUB_TOKEN` and `HF_TOKEN` for API access. Reddit and HN use free RSS/API (no auth).

## Docker Deployment

```bash
docker build -t nous-gtm:latest .
docker rm -f nous-gtm
docker run -d --name nous-gtm --network tvl-bridge --restart unless-stopped -p 8050:8050 nous-gtm:latest
```

Traefik routes `nous.trillionverselabs.com` → `localhost:8050`.

## Verification

Run `scripts/verify.sh` to check:

1. `curl -s http://localhost:8050/prototype` returns the dashboard
2. No fabricated dollar values in cluster bars or drill-downs
3. Funnel shows stage names only, not specific metrics
4. Competitor counts match `signal_discovery.db` query
5. Banner text accurately says "real signal" vs "method/heuristic"
6. Click handlers work (toggleCluster, toggleFunnel, toggleCompetitor)
7. Drill-down panels display correctly

## GTM Thesis

214K developers chose Hermes for open weights and transparent pricing. This dashboard shows the real friction developers surface in public — where they critique closed-model APIs and switch to open source alternatives for cost, control, and compliance reasons.

## License

MIT.
