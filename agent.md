# Agent Instructions — Nous GTM Prototype

## Purpose

This agent builds and maintains the Nous GTM Signal Discovery Dashboard at `/prototype`. It is a portfolio artifact demonstrating GTM strategy for Nous Research — proving the ability to find, cluster, and analyze real developer signal that directly maps to revenue opportunities.

## Scope

This repo contains ONLY the prototype page code: signal collection pipeline, SQLite signal database, and the clustered pain-point dashboard. The portfolio pages (board memo, problem, approach, role, resume, etc.) are in `portfolio_data.py` which is excluded from this repository via `.gitignore`.

## Core Principles

1. **Honesty over polish.** Every number must be traceable. If it's modeled/estimated, say so. If it's real signal, link to the source. Never let a fabricated dollar figure sit next to real data — it contaminates the real data.

2. **Structure over fake numbers.** The conversion funnel shows stage structure and instrumentation plan, not invented metrics. A CEO glancing at this should understand what would be tracked, not be misled by specific Nous figures.

3. **Real data wins.** Cluster signal counts, source links, competitor mention counts — these come from `signal_discovery.db` which is populated by `run_prototype.py` hitting live public APIs. If the DB doesn't have it, don't make it up.

## Data Integrity Rules

- `competitor_friction.json` must match counts from `SELECT COUNT(*) FROM signals WHERE competitors LIKE '%openai%'`
- Cluster `count` and `signal_frequency_score` must come from the database, not hardcoded in PROTOTYPE_DATA
- `monetary_value` must NEVER be auto-calculated from score × constant. Either real data supports it, or it doesn't appear at all.
- Funnel numbers must be stage names + methodology only. No "$34.2M" — that reads as a real Nous metric.

## File Responsibilities

- `app.py` — Flask routes, template data prep, DB queries. Serves `/prototype`, `/health`, `/robots.txt`. Conditionally imports `portfolio_data.py` (not in this repo).
- `templates/prototype.html` — Jinja2 dashboard. Three-column layout: funnel | clusters | friction. No Pipeline section — that content lives in README.md.
- `templates/base.html` — Shared layout. No navigation menu in this public repo — the prototype page is standalone for code review by Nous Research engineers.
- `static/css/styles.css` — Design system (TVL tokens). Dashboard cards use thin colored outlines (cyan/purple/green). Blue = var(--cyan).
- `run_prototype.py` — Signal collection from HN, GitHub, HF, Reddit.
- `output/` — JSON files that feed the template. Excluded from repo via .gitignore (regenerated on each run).
- `signal_discovery.db` — SQLite database. Excluded from repo via .gitignore (regenerated on each run).

## Dashboard Card Styling

Three-column dashboard uses thin colored outline classes:

- Column 1 (Conversion Funnel): `card-cyan-thin`
- Column 2 (Pain Point Clusters): `card-purple-thin`
- Column 3 (Competitor Friction): `card-green-thin`

All cards: 1px colored border, hover reveals full color + shadow + slight lift. Matches the snapshot page card treatment.

## Deployment

```bash
# Rebuild after any change
cd /home/lisaalfa/jobsearch/nous-gtm-app
docker build -t nous-gtm:latest .
docker rm -f nous-gtm
docker run -d --name nous-gtm --network tvl-bridge --restart unless-stopped \
  -p 8050:8050 \
  -v /home/lisaalfa/.hermes/profiles/charlene:/app/.hermes:ro \
  nous-gtm:latest
```

The volume mount (`-v ...:/app/.hermes:ro`) is REQUIRED for the `/api/agent-status` endpoint to serve live cron job data from `~/.hermes/profiles/charlene/cron/jobs.json`. Without it, the endpoint falls back to default placeholder jobs.

Traefik routes `nous.trillionverselabs.com` → localhost:8050.

## Verification Checklist

Before claiming deployment is complete:

1. `curl -s http://localhost:8050/prototype` returns the dashboard
2. No fabricated dollar values in cluster bars or drill-downs
3. Funnel shows stage names only, not specific metrics
4. Competitor counts match `signal_discovery.db` query
5. Banner text accurately says "real signal" vs "method/heuristic"
6. Click handlers work: toggleCluster, toggleFunnel, toggleCompetitor
7. Drill-down panels display correctly (cloneNode + display:block)
8. Stats + Data Sources are side-by-side (compact layout), not stacked
9. No "REAL SIGNAL" duplicate banner at page bottom
10. `/api/agent-status` returns JSON array of cron jobs when `.hermes` is mounted
