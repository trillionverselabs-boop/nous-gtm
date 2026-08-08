#!/usr/bin/env python3
"""
run_prototype.py — Signal Discovery Ingestion Script

Pulls real public developer signal about Hermes Agent / Nous Research from API
sources, stores it in SQLite, then clusters it via keyword heuristics.
Also tags competitor mentions (Anthropic, OpenAI, Google, xAI) for friction analysis.

Data sources:
  1. HN Algolia API     — no auth needed
  2. GitHub API          — needs GITHUB_TOKEN
  3. HuggingFace API     — needs HF_API_KEY
  4. Reddit API          — free JSON API (no OAuth needed)

Usage:
  python run_prototype.py                    # Full run: ingest + cluster
  python run_prototype.py --ingest-only      # Only pull raw data
  python run_prototype.py --scan github      # Only scan one source

FACTS ONLY. No fabricated data, no invented metrics, no estimated figures.
"""
import os
import sys
import json
import time
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime, timezone

# ─── Config ────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "signal_discovery.db"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

NOUS_REPOS = [
    "NousResearch/hermes-agent",
    "NousResearch/Hermes-Agent",
    "NousResearch/Psyche",
    "NousResearch/DisTrO",
]

HN_QUERIES = ["Hermes Agent", "Nous Research", "open weights AI", "self-hosted LLM"]
HF_MODELS = ["NousResearch", "Nous-Research"]
REDDIT_SUBREDDITS = ["LocalLLaMA", "MachineLearning"]
REDDIT_SEARCH = ["Hermes Agent", "Nous Research", "open weights"]

# Terms that indicate security incidents / unrelated content — filtered out
# so we only surface real developer pain points, not cyberattack reports.
EXCLUDE_TERMS = [
    "attack", "breach", "cybersecurity", "security attack",
    "exploit", "malware", "ransomware", "hacked",
    "data breach", "cyber attack", "cyberattack",
]

# Competitor mention keywords — used to tag each signal for friction analysis.
# When a signal mentions one of these, we record it so we can build
# "friction by competitor" visualizations.
COMPETITOR_KEYWORDS = {
    "anthropic": ["anthropic", "claude"],
    "openai": ["openai", "gpt-4", "gpt-4o", "gpt-4.5", "o1", "o3", "o4"],
    "google": ["google", "gemini", "bard", "vertex"],
    "xai": ["xai", "grok", "elon"],
}

# ─── SQLite ────────────────────────────────────────────────────────────────────

def init_db():
    """Create signal_discovery.db if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source      TEXT NOT NULL,          -- 'github', 'hn', 'huggingface', 'reddit'
            platform_id TEXT NOT NULL,          -- repo_issue_number, hn_item_id, etc.
            timestamp   TEXT NOT NULL,          -- ISO 8601
            raw_text    TEXT NOT NULL,
            url         TEXT NOT NULL,
            signal_strength REAL DEFAULT 0.5,   -- 0-1, heuristic based on engagement
            metadata    TEXT,                  -- JSON: author, score, comments, etc.
            competitor  TEXT,                  -- first competitor mentioned, or NULL
            competitors TEXT,                  -- JSON array of all competitors mentioned
            UNIQUE(source, platform_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON signals(source)")
    # NOTE: idx_competitor and idx_timestamp are created after migration below
    conn.commit()

    # Migration: if table existed without competitor columns, add them
    cols = [r[1] for r in conn.execute("PRAGMA table_info(signals)").fetchall()]
    if "competitor" not in cols:
        conn.execute("ALTER TABLE signals ADD COLUMN competitor TEXT")
    if "competitors" not in cols:
        conn.execute("ALTER TABLE signals ADD COLUMN competitors TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_competitor ON signals(competitor)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON signals(timestamp DESC)")
    conn.commit()
    return conn


def _should_exclude(text):
    """Return True if this signal mentions security incidents or unrelated topics."""
    text_lower = text.lower()
    return any(term in text_lower for term in EXCLUDE_TERMS)


def _detect_competitors(text):
    """Return list of competitors mentioned in the text."""
    text_lower = text.lower()
    found = []
    for comp, keywords in COMPETITOR_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            found.append(comp)
    return found


def store_signal(conn, source, platform_id, timestamp, raw_text, url, signal_strength, metadata=None):
    """Insert a signal, skipping duplicates and security-incident content."""
    if _should_exclude(raw_text):
        return False

    competitors = _detect_competitors(raw_text)
    competitor = competitors[0] if competitors else None

    conn.execute(
        "INSERT OR IGNORE INTO signals "
        "(source, platform_id, timestamp, raw_text, url, signal_strength, metadata, competitor, competitors) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (source, platform_id, timestamp, raw_text, url, signal_strength,
         json.dumps(metadata) if metadata else None,
         competitor,
         json.dumps(competitors) if competitors else None))
    conn.commit()
    return True


# ─── Layer 1: Data Sources ────────────────────────────────────────────────────

def scan_github(conn):
    """Scan GitHub repos for Hermes usage signals."""
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("[GitHub] No GITHUB_TOKEN found — skipping (set in .env)")
        return 0

    import urllib.request
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    total = 0

    for repo in NOUS_REPOS:
        search_url = f"https://api.github.com/search/issues?q=hermes+repo:{repo}+type:issue&per_page=50"
        try:
            req = urllib.request.Request(search_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            for item in data.get("items", []):
                text = (item.get("title", "") + " " + item.get("body", "")).strip()
                if text:
                    if store_signal(
                        conn, "github", f"{repo}#{item['number']}",
                        item.get("created_at", datetime.now(timezone.utc).isoformat()),
                        text[:500], item.get("html_url", ""),
                        min(1.0, item.get("comments", 0) / 10.0 + 0.5),
                        {"repo": repo, "author": item.get("user", {}).get("login"), "comments": item.get("comments", 0)}
                    ):
                        total += 1
            time.sleep(1)  # rate limit
        except Exception as e:
            print(f"[GitHub] Error scanning {repo}: {e}")

    print(f"[GitHub] Collected {total} signals")
    return total


def scan_hn(conn):
    """Scan Hacker News via Algolia API."""
    import urllib.request
    import urllib.parse
    total = 0

    for query in HN_QUERIES:
        encoded_query = urllib.parse.quote(query)
        url = f"https://hn.algolia.com/api/v1/search?query={encoded_query}&hitsPerPage=50"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            for hit in data.get("hits", []):
                text = (hit.get("title", "") + " " + (hit.get("text", "") or "")).strip()
                if text:
                    ts = datetime.fromtimestamp(hit.get("created_utc", 0), tz=timezone.utc).isoformat()
                    points = hit.get("points", 0)
                    age_days = max(1, (datetime.now(timezone.utc).timestamp() - hit.get("created_utc", 0)) / 86400)
                    strength = min(1.0, points / (age_days * 10))
                    if store_signal(
                        conn, "hn", str(hit.get("objectID", "")),
                        ts, text[:500],
                        hit.get("url", f"https://news.ycombinator.com/item?id={hit.get('objectID')}"),
                        max(0.3, strength),
                        {"points": points, "author": hit.get("author")}
                    ):
                        total += 1
            time.sleep(0.5)
        except Exception as e:
            print(f"[HN] Error scanning '{query}': {e}")

    print(f"[HN] Collected {total} signals")
    return total


def scan_huggingface(conn):
    """Scan HuggingFace for Nous model discussions."""
    token = os.getenv("HF_API_KEY") or os.getenv("HF_TOKEN")
    if not token:
        print("[HuggingFace] No HF_API_KEY found — skipping (set in .env)")
        return 0

    import urllib.request
    headers = {"Authorization": f"Bearer {token}"}
    total = 0

    for model_org in HF_MODELS:
        url = f"https://huggingface.co/api/models?author={model_org}&limit=10"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                models = json.loads(resp.read().decode())
            for model in models:
                model_id = model.get("id", "")
                disc_url = f"https://huggingface.co/api/models/{model_id}/discussions"
                try:
                    req2 = urllib.request.Request(disc_url, headers=headers)
                    with urllib.request.urlopen(req2, timeout=15) as resp2:
                        discussions = json.loads(resp2.read().decode())
                    # HF discussions API may return a dict with pagination, or a list directly
                    if isinstance(discussions, dict):
                        discussions = discussions.get("discussions", discussions.get("data", []))
                    elif not isinstance(discussions, list):
                        discussions = []
                    for d in discussions:
                        if isinstance(d, str):
                            continue  # skip string entries (pagination cursors, etc.)
                        text = (d.get("title", "") + " " + str(d.get("content", "") or "")).strip()
                        if text:
                            ts = d.get("created_at", datetime.now(timezone.utc).isoformat())
                            if store_signal(
                                conn, "huggingface", f"{model_id}#{d.get('id', '')}",
                                ts, text[:500],
                                f"https://huggingface.co/{model_id}/discussions/{d.get('id', '')}",
                                min(1.0, d.get("num_comments", 0) / 5.0 + 0.5),
                                {"model": model_id, "author": d.get("author", {}).get("name"), "comments": d.get("num_comments", 0)}
                            ):
                                total += 1
                except Exception as e:
                    print(f"[HuggingFace] Error fetching discussions for {model_id}: {e}")
                time.sleep(1)
        except Exception as e:
            print(f"[HuggingFace] Error listing models for {model_org}: {e}")

    print(f"[HuggingFace] Collected {total} signals")
    return total


def scan_reddit(conn):
    """Scan Reddit via RSS feeds (no OAuth, no subscription needed).

    Reddit's public JSON API (.json endpoints) now returns 403 for most requests.
    The RSS feeds (.rss) remain publicly accessible without authentication.
    We parse the RSS XML and filter for Hermes/Nous/open-weights mentions.
    """
    import urllib.request
    import re
    from xml.etree import ElementTree as ET
    total = 0

    NS = {"atom": "http://www.w3.org/2005/Atom"}

    for subreddit in REDDIT_SUBREDDITS:
        url = f"https://www.reddit.com/r/{subreddit}/.rss"
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read().decode()
            root = ET.fromstring(content)

            for entry in root.findall("entry", NS):
                title_elem = entry.find("title", NS)
                title = (title_elem.text or "") if title_elem is not None else ""
                link_elem = entry.find("link", NS)
                url_href = link_elem.get("href") if link_elem is not None else ""

                content_elem = entry.find("{http://www.w3.org/2005/Atom}content", NS)
                if content_elem is None:
                    content_elem = entry.find("content", NS)
                summary = ""
                if content_elem is not None and content_elem.text:
                    summary = content_elem.text

                # Check for relevant AI developer signal keywords
                full_text = (title + " " + summary).lower()
                hermes_related = any(term in full_text for term in [
                    "hermes", "nous", "open weights", "open-weight", "self-hosted",
                    "self host", "local llm", "local-ai", "locallm",
                ])
                if not hermes_related:
                    continue

                text = (title + " " + summary).strip()
                if text:
                    published = entry.find("published", NS)
                    ts = (published.text or datetime.now(timezone.utc).isoformat()) if published is not None else datetime.now(timezone.utc).isoformat()
                    # Strip HTML tags from summary for plain text
                    clean_summary = re.sub(r"<[^>]+>", " ", summary)[:300] if summary else ""
                    text_clean = (title + " " + clean_summary).strip()[:500]
                    post_id = url_href.split("/")[-2] if url_href and url_href.endswith("/") else (url_href.split("/")[-1] if url_href else "")
                    if store_signal(
                        conn, "reddit", f"{subreddit}_{post_id}",
                        ts, text_clean, url_href,
                        0.7,  # default signal strength for RSS (no score available)
                        {"subreddit": subreddit, "source": "rss"}
                    ):
                        total += 1

            time.sleep(3)  # be polite to Reddit
        except Exception as e:
            print(f"[Reddit] Error fetching r/{subreddit} RSS: {e}")

    print(f"[Reddit] Collected {total} signals")
    return total


# ─── Layer 2: Ingestion ────────────────────────────────────────────────────────
# (data is stored in SQLite above — no separate step needed)

# ─── Layer 3: Clustering & Scoring ────────────────────────────────────────────

def cluster_signals(conn):
    """Group raw signals into pain-point clusters. Each cluster has real linked sources."""
    rows = conn.execute(
        "SELECT source, timestamp, raw_text, url, signal_strength, metadata, competitor, competitors "
        "FROM signals ORDER BY timestamp DESC LIMIT 500"
    ).fetchall()

    if not rows:
        print("[Cluster] No signals found — run without --ingest-only first")
        return []

    print(f"[Cluster] Clustering {len(rows)} signals")
    clusters, competitor_friction = _heuristic_cluster(rows)
    print(f"[Cluster] Produced {len(clusters)} clusters")
    return clusters, competitor_friction


_CLUSTER_KEYWORDS = {
    "Community & Support": ["support", "community", "help", "question", "issue", "bug", "fix", "troubleshoot"],
    "Deployment & Infrastructure": ["deploy", "docker", "production", "self-hosted", "on-prem", "infrastructure", "server", "host", "vps"],
    "Developer Experience Friction": ["setup", "config", "difficult", "hard", "install", "vram", "requirement", "guide", "tutorial", "beginner"],
    "Model Capabilities & Features": ["feature", "capability", "missing", "want", "need", "tool", "plugin", "skill", "extension"],
    "Cost & API Pricing": ["cost", "save", "expensive", "token", "budget", "openai", "anthropic", "price", "pay", "dollar"],
}

_CLUSTER_DESCRIPTIONS = {
    "Community & Support": "Community support requests, bug reports, and troubleshooting threads.",
    "Developer Experience Friction": "Pain points around setup, configuration, and ongoing maintenance of local deployments.",
    "Deployment & Infrastructure": "Real-world deployment patterns, self-hosting challenges, and infrastructure decisions.",
    "Model Capabilities & Features": "Requests and discussions about specific capabilities, tools, and feature gaps.",
    "Cost & API Pricing": "Developer sentiment on switching from paid APIs to self-hosted open weights to reduce token costs and rate limits.",
}


def _heuristic_cluster(rows):
    """Keyword-based clustering — each cluster must have at least one real source."""
    cluster_results = []
    competitor_friction = {}

    for name, kws in _CLUSTER_KEYWORDS.items():
        matched = []
        for r in rows:
            text_lower = r[2].lower() if r[2] else ""
            if any(kw in text_lower for kw in kws):
                matched.append({
                    "platform": r[0],
                    "url": r[3],
                    "excerpt": r[2][:200] if r[2] else "",
                    "competitor": r[6] if r[6] else None,
                    "competitors": json.loads(r[7]) if r[7] else [],
                    "_strength": r[4],  # signal strength for sorting
                })

            # Also track competitor mentions across ALL signals
            competitors_raw = r[7]
            if competitors_raw:
                try:
                    comps = json.loads(competitors_raw) if isinstance(competitors_raw, str) else competitors_raw
                    for c in comps:
                        competitor_friction[c] = competitor_friction.get(c, 0) + 1
                except (json.JSONDecodeError, TypeError):
                    pass

        if matched:
            total_matched = len(matched)
            # Ensure source diversity: sort by strength, then interleave platforms
            matched.sort(key=lambda x: x["_strength"], reverse=True)
            platforms_shown = set()
            diverse = []
            for m in matched:
                if m["platform"] not in platforms_shown:
                    diverse.append(m)
                    platforms_shown.add(m["platform"])
            for m in matched:
                if len(diverse) >= 8:
                    break
                if m not in diverse:
                    diverse.append(m)
            matched = diverse
            for m in matched:
                m.pop("_strength", None)

            avg_strength = sum(r[4] for r in rows if any(kw in (r[2] or "").lower() for kw in kws)) / max(1, total_matched)
            score = round(50 + avg_strength * 40, 1)  # range: 50-90
            tier = "High" if total_matched >= 40 else ("Medium" if total_matched >= 10 else "Low")
            cluster_results.append({
                "id": len(cluster_results) + 1,
                "name": name,
                "description": _CLUSTER_DESCRIPTIONS.get(name, ""),
                "count": total_matched,
                "signal_frequency_score": score,
                "tier": tier,
                "sources": matched[:8],
            })

    cluster_results.sort(key=lambda x: x["count"], reverse=True)
    for i, c in enumerate(cluster_results):
        c["id"] = i + 1

    return cluster_results, competitor_friction


# ─── Layer 4: Output ───────────────────────────────────────────────────────────

def write_clusters(clusters, competitor_friction):
    """Write clustered output for the dashboard to consume."""
    output_path = OUTPUT_DIR / "clustered_pain_points.json"
    with open(output_path, "w") as f:
        json.dump(clusters, f, indent=2)
    print(f"[Output] Wrote {len(clusters)} clusters to {output_path}")

    compet_output = OUTPUT_DIR / "competitor_friction.json"
    with open(compet_output, "w") as f:
        json.dump({k: v for k, v in sorted(competitor_friction.items(), key=lambda x: x[1], reverse=True)}, f, indent=2)
    print(f"[Output] Wrote {len(competitor_friction)} competitor friction entries to {compet_output}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Signal Discovery — ingest & cluster public developer signal")
    parser.add_argument("--ingest-only", action="store_true", help="Only pull raw data, skip clustering")
    parser.add_argument("--scan", choices=["github", "hn", "huggingface", "reddit"],
                        help="Scan only one source")
    args = parser.parse_args()

    conn = init_db()
    print(f"[Signal Discovery] Database: {DB_PATH}")
    print(f"[Signal Discovery] Started at {datetime.now(timezone.utc).isoformat()}")

    if args.scan:
        scanners = {
            "github": scan_github,
            "hn": scan_hn,
            "huggingface": scan_huggingface,
            "reddit": scan_reddit,
        }
        scanners[args.scan](conn)
    else:
        scan_github(conn)
        scan_hn(conn)
        scan_huggingface(conn)
        scan_reddit(conn)

    if args.ingest_only:
        count = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        print(f"[Signal Discovery] Total signals in DB: {count}")
        conn.close()
        return

    clusters, competitor_friction = cluster_signals(conn)
    write_clusters(clusters, competitor_friction)

    total = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    print(f"[Signal Discovery] Total signals: {total}")
    conn.close()
    print(f"[Signal Discovery] Completed at {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    main()
