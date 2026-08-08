"""
Nous GTM Signal Discovery Dashboard
Prototype app — the /prototype page only.

This repo contains the prototype page code: signal collection pipeline,
SQLite signal database, and the clustered pain-point dashboard.

The portfolio pages (board memo, role, resume, etc.) live in portfolio_data.py
which is excluded from this repository via .gitignore.

Routes:
  /prototype  - Signal discovery dashboard (interactive, 3-column)
  /health     - Health check
  /robots.txt - Crawl policy
"""
import os
import re
import sqlite3
import json
from pathlib import Path
from datetime import datetime

from flask import Flask, render_template, send_from_directory, Response

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static",
)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET", "dev-only-nous-gtm")

BASE_DIR = Path(__file__).parent

# ─── Prototype Data ─────────────────────────────────────────────────────────────
PROTOTYPE_DATA = {
    "title": "Signal Discovery",
    "subtitle": "Public developer signal about Hermes — collected from live APIs, clustered, and ranked.",
    "sources_status": [
        {"name": "HN Algolia", "description": "hn.algolia.com — real-time Hacker News stories about Hermes and open weights.", "access": "No auth required", "status": "Live", "badge": "badge-built"},
        {"name": "GitHub API", "description": "Issues and discussions on Nous public repos.", "access": "GITHUB_TOKEN in Vault", "status": "Live", "badge": "badge-built"},
        {"name": "HuggingFace API", "description": "Community discussions on Nous model pages.", "access": "HF_TOKEN in Vault", "status": "Live", "badge": "badge-built"},
        {"name": "Reddit RSS", "description": "r/LocalLLaMA and r/MachineLearning — public RSS feeds.", "access": "Free, no auth needed", "status": "Setup", "badge": "badge-dim"},
    ],
    "cluster_stats": [
        ("Total signals", "246", "cyan"),
        ("Clusters identified", "5", "purple"),
        ("High-priority clusters", "4", "green"),
        ("Avg. signal score", "71.3", "hermes"),
        ("Sources live", "3", "cyan"),
        ("Sources setup", "1", "dim"),
    ],
    "sample_clusters": [
        {
            "id": 1,
            "name": "Community & Support",
            "description": "Community support requests, bug reports, and troubleshooting threads.",
            "count": 66,
            "signal_frequency_score": 75.1,
            "tier": "High",
            "badge": "badge-built",
            "sources": [
                {"platform": "github", "url": "https://github.com/NousResearch/hermes-agent/issues/80204", "excerpt": "[Bug]: Hermes Desktop leaves orphaned processes after exit/update"},
                {"platform": "github", "url": "https://github.com/NousResearch/hermes-agent/issues/79381", "excerpt": "Dispatch-tick integration — oversized SL3 planning epic"},
                {"platform": "github", "url": "https://github.com/NousResearch/hermes-agent/issues/79021", "excerpt": "Fix npm dependency vulnerabilities reported by hermes doctor"},
            ],
        },
        {
            "id": 2,
            "name": "Deployment & Infrastructure",
            "description": "Real-world deployment patterns, self-hosting challenges, and infrastructure decisions.",
            "count": 61,
            "signal_frequency_score": 64.5,
            "tier": "High",
            "badge": "badge-built",
            "sources": [
                {"platform": "github", "url": "https://github.com/NousResearch/hermes-agent/issues/76416", "excerpt": "Hermes WebUI on Hostinger VPS — open-weights deployment still harder than Heroku"},
                {"platform": "github", "url": "https://github.com/NousResearch/hermes-agent/issues/74557", "excerpt": "Zalo integration request — community wants more messaging platform support"},
                {"platform": "github", "url": "https://github.com/NousResearch/hermes-agent/issues/70542", "excerpt": "doctor misses volatile HERMES_HOME filesystems"},
            ],
        },
        {
            "id": 3,
            "name": "Developer Experience Friction",
            "description": "Pain points around setup, configuration, and ongoing maintenance of local deployments.",
            "count": 50,
            "signal_frequency_score": 73.7,
            "tier": "High",
            "badge": "badge-built",
            "sources": [
                {"platform": "huggingface", "url": "https://huggingface.co/NousResearch/Hermes-4-70B/discussions/", "excerpt": "hardware specs for running RTX Pro 6000"},
                {"platform": "huggingface", "url": "https://huggingface.co/NousResearch/Hermes-4-14B/discussions/", "excerpt": "generation_config.json eos_token_id issue causing runaway generation"},
                {"platform": "github", "url": "https://github.com/NousResearch/hermes-agent/issues/79415", "excerpt": "Local AI inside Hermes — memory save too slow"},
                {"platform": "github", "url": "https://github.com/NousResearch/hermes-agent/issues/78636", "excerpt": "Shard hermes_state.py (god-file decomposition)"},
            ],
        },
        {
            "id": 4,
            "name": "Model Capabilities & Features",
            "description": "Requests and discussions about specific capabilities, tools, and feature gaps.",
            "count": 42,
            "signal_frequency_score": 73.8,
            "tier": "High",
            "badge": "badge-built",
            "sources": [
                {"platform": "github", "url": "https://github.com/NousResearch/hermes-agent/issues/79415", "excerpt": "Local AI inside Hermes — memory save too slow"},
                {"platform": "github", "url": "https://github.com/NousResearch/hermes-agent/issues/79021", "excerpt": "Fix npm dependency vulnerabilities"},
                {"platform": "github", "url": "https://github.com/NousResearch/hermes-agent/issues/76894", "excerpt": "Hermes contribution lifecycle skill set"},
            ],
        },
        {
            "id": 5,
            "name": "Cost & API Pricing",
            "description": "Developer sentiment on switching from paid APIs to self-hosted open weights to reduce token costs and rate limits.",
            "count": 23,
            "signal_frequency_score": 69.3,
            "tier": "Medium",
            "badge": "badge-hermes",
            "sources": [
                {"platform": "huggingface", "url": "https://huggingface.co/NousResearch/Hermes-4-14B/discussions/", "excerpt": "generation_config.json eos_token_id issue"},
                {"platform": "github", "url": "https://github.com/NousResearch/hermes-agent/issues/79415", "excerpt": "Local AI inside Hermes — memory save too slow"},
                {"platform": "github", "url": "https://github.com/NousResearch/hermes-agent/issues/68564", "excerpt": "Desktop: file upload saves to /.hermes instead of HERMES_HOME"},
            ],
        },
    ],
}

# ─── Routes ─────────────────────────────────────────────────────────────────────

def _summarize_competitor_signal(comp, raw_text):
    """Convert a raw developer signal into a layman's summary for competitor drill-downs."""
    if not raw_text:
        return f"Developer feedback mentioning {comp} — cost, rate limits, or vendor-lock concerns"

    # Strip markdown/headers to get to the actual complaint
    text = raw_text.replace("\n\n", " ").replace("\n", " ").strip()
    # Remove leading markdown headers (###, ##, #) and GitHub labels like [Bug]:
    text = re.sub(r'^[#]+\s*', '', text)
    text = re.sub(r'^\[[\w\s]+\]:\s*', '', text)
    text_lower = text.lower()

    # ── Anthropic: catch performance, pricing, limits, bans ──
    if comp == "anthropic":
        if "banned" in text_lower or "suspend" in text_lower or "rate limit" in text_lower:
            return "Developer hit Anthropic API limits or account restrictions blocking production use"
        if "price" in text_lower or "cost" in text_lower or "expens" in text_lower or "bill" in text_lower:
            return "Anthropic pricing drove developer to seek cheaper open-weights alternative"
        if "performance" in text_lower or "degrad" in text_lower or "wors" in text_lower or "regress" in text_lower:
            return "Developer experienced Anthropic model performance degradation — migrated to Hermes"
        if "running out" in text_lower or "out of claude" in text_lower:
            return "Developer ran out of Claude credits — switched to self-hosted Hermes"
        if "api" in text_lower or "format" in text_lower or "break" in text_lower:
            return "Anthropic API changes forced developer to migrate to Hermes"
        if "claude" in text_lower and ("switch" in text_lower or "migrat" in text_lower or "alt" in text_lower or "self-host" in text_lower):
            return "Developer switching from Claude to self-hosted Hermes for reliability"
        # Fallback: strip the title, use first meaningful sentence
        clean = re.sub(r'[#]+\s*', '', text).strip()
        if "Claude" in clean or "claude" in clean:
            return f"Developer feedback about Anthropic/Claude: {clean[:130]}"
        return f"Developer feedback mentioning Anthropic — considering alternatives"

    # ── OpenAI ──
    if comp == "openai":
        if "rate limit" in text_lower or "rpm" in text_lower or "throttle" in text_lower:
            return "Developer hit OpenAI rate limits that blocked their production pipeline"
        if "bill" in text_lower or "cost" in text_lower or "expens" in text_lower or "$" in text:
            return "OpenAI costs scaled unexpectedly — developer looking for cheaper alternative"
        if "api" in text_lower or "format" in text_lower or "break" in text_lower:
            return "OpenAI API changed or broke — developer migrated to Hermes for stability"
        if "sam altman" in text_lower or "open weight" in text_lower or "open source" in text_lower:
            return "Developer tracking OpenAI's open-weights policy shifts — considering Hermes"
        clean = re.sub(r'[#]+\s*', '', text).strip()
        if clean:
            return f"Developer feedback mentioning OpenAI: {clean[:130]}"
        return "Developer feedback mentioning OpenAI — evaluating alternatives"

    # ── Google ──
    if comp == "google":
        if "rate limit" in text_lower or "quota" in text_lower:
            return "Developer hit Google API quotas limiting their production usage"
        if "cost" in text_lower or "expens" in text_lower or "bill" in text_lower:
            return "Google costs pushed developer toward open-weights alternative"
        if "auth" in text_lower or "token" in text_lower:
            return "Google authentication complexity drove developer to Hermes"
        clean = re.sub(r'[#]+\s*', '', text).strip()
        if clean:
            return f"Developer feedback mentioning Google AI: {clean[:130]}"
        return "Developer feedback mentioning Google AI — evaluating alternatives"

    # ── xAI ──
    if comp == "xai":
        if "rate limit" in text_lower or "quota" in text_lower:
            return "Developer hit xAI rate limits affecting their pipeline"
        if "cost" in text_lower or "expens" in text_lower or "bill" in text_lower:
            return "xAI pricing drove developer to open-weights alternative"
        if "grok" in text_lower:
            return "Developer exploring Grok integration with self-hosted Hermes setup"
        clean = re.sub(r'[#]+\s*', '', text).strip()
        if clean:
            return f"Developer feedback mentioning xAI: {clean[:130]}"
        return "Developer feedback mentioning xAI — evaluating alternatives"

    return f"Developer feedback about {comp} — {text[:120]}"


@app.route("/prototype")
def prototype():
    """Signal discovery dashboard — clustered pain points from public developer signal."""
    # Load dynamically clustered data if available, fall back to sample
    clustered_file = BASE_DIR / "output" / "clustered_pain_points.json"
    cluster_data = None
    if clustered_file.exists():
        try:
            with open(clustered_file) as f:
                loaded = json.load(f)
            if loaded:
                cluster_data = loaded
        except (json.JSONDecodeError, IOError):
            pass

    # Load competitor friction data
    competitor_data = {}
    friction_file = BASE_DIR / "output" / "competitor_friction.json"
    if friction_file.exists():
        try:
            with open(friction_file) as f:
                competitor_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    # If no live DB data, compute competitor friction from SQLite
    db_path = BASE_DIR / "signal_discovery.db"
    if db_path.exists() and not competitor_data:
        try:
            conn = sqlite3.connect(str(db_path))
            for comp in ["openai", "anthropic", "google", "xai"]:
                count = conn.execute(
                    "SELECT COUNT(*) FROM signals "
                    "WHERE competitors IS NOT NULL "
                    "AND LOWER(competitors) LIKE ?",
                    [f"%\"{comp}\"%"]
                ).fetchone()[0]
                if count > 0:
                    competitor_data[comp] = count
            conn.close()
        except Exception:
            pass

    # If no competitor data yet, use sample from PROTOTYPE_DATA fallback
    if not competitor_data:
        competitor_data = {"openai": 9, "anthropic": 4, "google": 1, "xai": 0}

    # Fetch real competitor evidence from SQLite for drill-down context
    competitor_evidence = {}
    db_path = BASE_DIR / "signal_discovery.db"
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            for comp in ["openai", "anthropic", "google", "xai"]:
                if competitor_data.get(comp, 0) > 0:
                    cursor = conn.execute(
                        "SELECT DISTINCT source, raw_text, url FROM signals "
                        "WHERE competitors IS NOT NULL AND LOWER(competitors) LIKE ? "
                        "ORDER BY signal_strength DESC",
                        [f"%{comp}%"]
                    )
                    platform_map = {"github": "github", "hn": "hn",
                                    "huggingface": "huggingface", "reddit": "reddit"}
                    evidence = []
                    seen_urls = set()
                    for row in cursor.fetchall():
                        url = row[2] or ""
                        if url in seen_urls:
                            continue
                        seen_urls.add(url)
                        raw = row[1] if row[1] else ""
                        summary = _summarize_competitor_signal(comp, raw)
                        evidence.append({
                            "platform": platform_map.get(row[0], row[0]),
                            "excerpt": summary,
                            "raw_excerpt": raw[:180] if raw else "",
                            "url": url,
                        })
                        if len(evidence) >= 5:
                            break
                    competitor_evidence[comp] = evidence
            conn.close()
        except Exception:
            pass

    # Merge: use live clusters if available, else fall back to sample data
    pd = dict(PROTOTYPE_DATA)
    if cluster_data:
        for c in cluster_data:
            if "badge" not in c:
                tier = c.get("tier", "Low")
                c["badge"] = {
                    "High": "badge-built",
                    "Medium": "badge-hermes",
                    "Low": "badge-spec",
                }.get(tier, "badge-hermes")
        pd["sample_clusters"] = cluster_data

        # Compute real stats from the database
        total_signals = 0
        if db_path.exists():
            try:
                conn = sqlite3.connect(str(db_path))
                total_signals = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
                source_counts = dict(conn.execute(
                    "SELECT source, COUNT(*) FROM signals GROUP BY source"
                ).fetchall())
                high_count = sum(1 for c in cluster_data if c.get("tier") == "High")
                avg_signal = round(
                    sum(c.get("signal_frequency_score", c.get("trust_score", 0)) for c in cluster_data)
                    / max(1, len(cluster_data)), 1
                )
                live_sources = len(source_counts)
                all_sources = {"github": "GitHub API", "hn": "HN Algolia",
                               "huggingface": "HuggingFace API", "reddit": "Reddit API"}
                setup_sources = len([s for s in all_sources if s not in source_counts])
                pd["cluster_stats"] = [
                    ("Total signals", str(total_signals), "cyan"),
                    ("Clusters identified", str(len(cluster_data)), "purple"),
                    ("High-priority clusters", str(high_count), "green"),
                    ("Avg. signal score", str(avg_signal), "hermes"),
                    ("Sources live", str(live_sources), "cyan"),
                    ("Sources setup", str(setup_sources), "dim"),
                ]
                conn.close()
            except Exception:
                pass

    # Compute max competitor count and max cluster count for percentage calculations
    max_comp_count = max(competitor_data.values()) if competitor_data else 1
    max_cluster_count = max(
        (c.get("count", 0) for c in pd["sample_clusters"]), default=1
    ) if pd.get("sample_clusters") else 1

    # Try to load portfolio data for nav links (not in public repo)
    portfolio_data = None
    try:
        from portfolio_data import PORTFOLIO_DATA
        portfolio_data = PORTFOLIO_DATA
    except ImportError:
        pass

    return render_template(
        "prototype.html",
        page_title="Signal Discovery Dashboard",
        prototype_data=pd,
        competitor_data=competitor_data,
        competitor_evidence=competitor_evidence,
        max_competitor=max_comp_count,
        max_cluster=max_cluster_count,
        portfolio_data=portfolio_data,
        active_page="prototype",
    )


@app.route("/health")
def health():
    return {"status": "ok", "app": "nous-gtm"}, 200


@app.route("/api/agent-status")
def agent_status():
    """Serve cron job status from local jobs.json for the dashboard."""
    import os, json
    from datetime import datetime, timezone

    jobs_file = "/app/.hermes/cron/jobs.json"
    default_jobs = [
        {"name": "tvl-site-health-2h", "state": "scheduled", "last_run": "recent"},
        {"name": "traefik-network-watchdog", "state": "scheduled", "last_run": "recent"},
        {"name": "r2p-pain-engine-weekly", "state": "paused", "last_run": "older"},
    ]

    try:
        with open(jobs_file, "r") as f:
            data = json.load(f)
        raw_jobs = data.get("jobs", []) if isinstance(data, dict) else data
    except Exception:
        raw_jobs = default_jobs

    # Normalize: pick the most relevant 8-agent syndicate jobs
    syndicate_jobs = [
        j for j in raw_jobs
        if any(k in j.get("name", "").lower() for k in [
            "pain-engine", "signal", "paper-ingest", "wiki", "site-health",
            "network-watchdog", "profile-backup", "job-scraper"
        ])
    ]
    # If filtering yields nothing, fall back to first 8
    if not syndicate_jobs:
        syndicate_jobs = raw_jobs[:8]
    syndicate_jobs = syndicate_jobs[:8]

    def fmt_last_run(j):
        ts = j.get("last_run_at") or j.get("last_run") or ""
        if not ts:
            return "never"
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.strftime("%b %d, %H:%M")
        except Exception:
            return ts[:19] if ts else "never"

    result = []
    for j in syndicate_jobs:
        result.append({
            "name": j.get("name", "unknown"),
            "state": j.get("state", j.get("enabled", "unknown")),
            "last_run": fmt_last_run(j),
            "schedule": j.get("schedule", ""),
        })

    return json.dumps(result), 200, {"Content-Type": "application/json"}


@app.route("/robots.txt")
def robots():
    sf = app.static_folder or "static"
    return send_from_directory(sf, "robots.txt"), 200, {"Content-Type": "text/plain"}


# ─── Portfolio routes (conditionally registered) ─────────────────────────────
try:
    from portfolio_data import register_portfolio_routes
    register_portfolio_routes(app)
except ImportError:
    # Portfolio data not available — only serve /prototype
    pass


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8050"))
    app.run(host="0.0.0.0", port=port)
