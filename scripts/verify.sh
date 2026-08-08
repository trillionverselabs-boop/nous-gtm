#!/bin/bash
# Hermes verification script for Nous GTM prototype
# Verifies all data integrity and UX fixes are live

set -e

HTML_URL="${Nous_GTM_URL:-http://localhost:8050/prototype}"
CSS_URL="${Nous_GTM_URL:-http://localhost:8050/static/css/styles.css}"

echo "=== Nous GTM Prototype Verification ==="
echo "URL: $HTML_URL"
echo

# Fetch fresh content
html=$(curl -sf "$HTML_URL" 2>/dev/null || curl -sf http://localhost:8050/prototype)
css=$(curl -sf "$CSS_URL" 2>/dev/null || curl -sf http://localhost:8050/static/css/styles.css)

# Verify files were read
if [ -z "$html" ]; then
    echo "FAIL - Could not fetch HTML"
    exit 1
fi
if [ -z "$css" ]; then
    echo "FAIL - Could not fetch CSS"
    exit 1
fi

# Save to temp files for Python parsing
echo "$html" > /tmp/_nous_html.html
echo "$css" > /tmp/_nous_css.css

python3 << 'PYEOF'
import sys

h = open('/tmp/_nous_html.html').read()
c = open('/tmp/_nous_css.css').read()

checks = [
    # Layout: drill-holder before dashboard
    ("Drill-holder before dashboard row",
     h.find('id="drill-holder"') < h.find('class="dashboard-row"')),

    # Layout: single drill-holder
    ("Single drill-holder div",
     h.count('<div id="drill-holder"></div>') == 1),

    # Layout: card padding tightened
    ("Dashboard card padding reduced",
     'padding: 12px;' in c),

    # Layout: gap reduced
    ("Dashboard row gap reduced",
     'gap: 10px' in c),

    # Layout: subtitle margins tighter
    ("Subtitle margins tightened",
     'margin-bottom: 8px' in h),

    # Cluster bars: compact height
    ("Cluster min-height 56px",
     'min-height: 56px' in c),

    ("Cluster gap 6px",
     'gap: 6px' in c),

    # Priority badge centered
    ("Priority badge centered",
     'text-align: center' in c[c.find('cluster-priority-badge'):c.find('cluster-priority-badge')+300]),

    # Data integrity: no fabricated dollar values
    ("No fabricated dollar values",
     '$748' not in h and '$647' not in h and 'est. value' not in h.lower()),

    # Funnel: stage names only, no numbers
    ("Funnel stage names only",
     'Agent Downloads' in h and 'Annualized Revenue' in h and 'funnel-kpi' not in h),

    # Competitor: real DB counts
    ("Competitor openai=9",
     '9 mention' in h),

    ("Competitor no fabricated counts",
     '32 HN' not in h and '41 GitHub' not in h),

    # Evidence table in drill-downs
    ("Pain point evidence table",
     'drill-evidence-table' in h),

    # Honest framing
    ("REAL SIGNAL badge",
     'REAL SIGNAL' in h),

    ("METHOD badge",
     'METHOD' in h),

    ("heuristic disclosure",
     'heuristic' in h.lower()),

    # Three-column layout
    ("Three-column dashboard",
     'dashboard-row' in h),

    # Interactivity
    ("showDrill JS function",
     'function showDrill' in h),

    ("toggleCluster JS",
     'function toggleCluster' in h),

    ("toggleCompetitor JS",
     'function toggleCompetitor' in h),

    # Bottom sections
    ("Stats section",
     'Stats' in h),

    ("Pipeline section",
     'Pipeline' in h),

    ("Data Sources section",
     'Data Sources' in h or 'Instrumentation' in h),
]

passed = sum(1 for _, ok in checks if ok)
for label, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")

if passed == len(checks):
    print(f"\n  {passed}/{len(checks)} — ALL CHECKS PASS —")
    sys.exit(0)
else:
    print(f"\n  {passed}/{len(checks)} — SOME CHECKS FAILED —")
    sys.exit(1)
PYEOF
