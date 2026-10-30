"""Generate GitHub profile stat cards as static SVG files.

Uses only the Python standard library and the GITHUB_TOKEN that GitHub Actions
provides automatically, so no personal token or secret is required.

Usage: python scripts/generate_stats.py USERNAME OUTPUT_DIR
Set STATS_FIXTURE=path.json to render from a local JSON file (offline test).
"""

import json
import os
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from html import escape

API = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN", "")

BG, BORDER, TITLE, TEXT, MUTED = "#0d1117", "#30363d", "#58a6ff", "#c9d1d9", "#8b949e"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
FALLBACK_COLOR = "#8b949e"
LANG_COLORS = {
    "Python": "#3572A5", "Jupyter Notebook": "#DA5B0B", "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6", "Shell": "#89e051", "Dockerfile": "#384d54",
    "C++": "#f34b7d", "C": "#555555", "Java": "#b07219", "HTML": "#e34c26",
    "CSS": "#563d7c", "R": "#198CE7", "MATLAB": "#e16737", "Go": "#00ADD8",
    "Rust": "#dea584", "SQL": "#e38c00", "Makefile": "#427819",
}
SKIPPED_LANGS = {"HTML", "CSS", "Jupyter Notebook"}


def _request(path, data=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "profile-stats"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(
        path if path.startswith("http") else API + path,
        data=json.dumps(data).encode() if data else None,
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch(user):
    profile = _request(f"/users/{user}")
    repos, page = [], 1
    while True:
        chunk = _request(f"/users/{user}/repos?per_page=100&type=owner&page={page}")
        repos += chunk
        if len(chunk) < 100:
            break
        page += 1
    repos = [r for r in repos if not r["fork"]]

    langs = Counter()
    for r in repos:
        try:
            langs.update(_request(r["languages_url"]))
        except Exception as exc:  # keep going if one repo fails
            print(f"warning: languages for {r['name']}: {exc}", file=sys.stderr)

    contributions = None
    try:
        query = (
            "query($login:String!){user(login:$login){contributionsCollection{"
            "contributionCalendar{totalContributions}"
            "totalCommitContributions totalPullRequestContributions "
            "totalIssueContributions totalPullRequestReviewContributions}}}"
        )
        res = _request("/graphql", {"query": query, "variables": {"login": user}})
        cc = res["data"]["user"]["contributionsCollection"]
        contributions = {
            "total": cc["contributionCalendar"]["totalContributions"],
            "commits": cc["totalCommitContributions"],
            "prs": cc["totalPullRequestContributions"],
            "issues": cc["totalIssueContributions"],
            "reviews": cc["totalPullRequestReviewContributions"],
        }
    except Exception as exc:
        print(f"warning: contributions unavailable: {exc}", file=sys.stderr)

    return {
        "user": user,
        "name": profile.get("name") or user,
        "followers": profile["followers"],
        "public_repos": len(repos),
        "stars": sum(r["stargazers_count"] for r in repos),
        "forks": sum(r["forks_count"] for r in repos),
        "since": profile["created_at"][:4],
        "languages": dict(langs),
        "contributions": contributions,
    }


def _frame(width, height, title, body):
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">'
        f'<rect x=".5" y=".5" width="{width - 1}" height="{height - 1}" rx="8" '
        f'fill="{BG}" stroke="{BORDER}"/>'
        f'<text x="24" y="36" font-family="{FONT}" font-size="18" font-weight="600" '
        f'fill="{TITLE}">{escape(title)}</text>{body}'
        f'<text x="{width - 24}" y="{height - 12}" text-anchor="end" font-family="{FONT}" '
        f'font-size="10" fill="{MUTED}">updated {stamp}</text></svg>'
    )


def overview_svg(d):
    c = d["contributions"]
    rows = [
        ("Public repositories", d["public_repos"]),
        ("Stars received", d["stars"]),
        ("Forks", d["forks"]),
        ("Followers", d["followers"]),
        ("On GitHub since", d["since"]),
    ]
    if c:
        rows = [
            ("Contributions, last year", c["total"]),
            ("Commits", c["commits"]),
            ("Pull requests", c["prs"]),
            ("Issues opened", c["issues"]),
            ("Code reviews", c["reviews"]),
        ] + rows
    row_h, top = 28, 62
    body = ""
    for i, (label, value) in enumerate(rows):
        y = top + i * row_h
        body += (
            f'<text x="24" y="{y}" font-family="{FONT}" font-size="14" fill="{TEXT}">'
            f"{escape(label)}</text>"
            f'<text x="446" y="{y}" text-anchor="end" font-family="{FONT}" font-size="14" '
            f'font-weight="600" fill="{TEXT}">{escape(str(value))}</text>'
        )
    height = top + len(rows) * row_h + 14
    return _frame(470, height, f"{d['name']}'s GitHub stats", body)


def languages_svg(d, limit=8):
    langs = {k: v for k, v in d["languages"].items() if k not in SKIPPED_LANGS}
    total = sum(langs.values()) or 1
    top = sorted(langs.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    bar_x, bar_w, bar_y = 24, 422, 54
    body, x = "", bar_x
    for name, size in top:
        w = bar_w * size / total
        color = LANG_COLORS.get(name, FALLBACK_COLOR)
        body += f'<rect x="{x:.1f}" y="{bar_y}" width="{w:.1f}" height="10" fill="{color}"/>'
        x += w
    body = f'<clipPath id="r"><rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="10" rx="5"/></clipPath><g clip-path="url(#r)">{body}</g>'
    for i, (name, size) in enumerate(top):
        col, row = i % 2, i // 2
        px, py = 24 + col * 215, 100 + row * 26
        color = LANG_COLORS.get(name, FALLBACK_COLOR)
        body += (
            f'<circle cx="{px + 5}" cy="{py - 4}" r="5" fill="{color}"/>'
            f'<text x="{px + 18}" y="{py}" font-family="{FONT}" font-size="13" fill="{TEXT}">'
            f"{escape(name)} <tspan fill=\"{MUTED}\">{size / total:.1%}</tspan></text>"
        )
    rows = (len(top) + 1) // 2
    return _frame(470, 100 + max(rows, 1) * 26 + 18, "Most used languages", body)


def main():
    user, out = sys.argv[1], sys.argv[2]
    fixture = os.environ.get("STATS_FIXTURE")
    data = json.load(open(fixture)) if fixture else fetch(user)
    os.makedirs(out, exist_ok=True)
    for fname, svg in (
        ("metrics-overview.svg", overview_svg(data)),
        ("metrics-languages.svg", languages_svg(data)),
    ):
        with open(os.path.join(out, fname), "w", encoding="utf-8") as fh:
            fh.write(svg)
        print(f"wrote {out}/{fname}")


if __name__ == "__main__":
    main()
