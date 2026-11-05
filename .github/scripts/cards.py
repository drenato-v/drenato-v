"""Gera os cards do perfil (estatísticas, linguagens e projetos) como SVG.

Roda dentro do GitHub Actions usando o GITHUB_TOKEN do próprio workflow,
então não depende do servidor público github-readme-stats.vercel.app.

Uso: python3 cards.py <usuario> <pasta_de_saida> <repo1> <repo2> ...
"""

import json
import os
import sys
import urllib.request
from html import escape

# Paleta Tokyo Night (a mesma usada no resto do README)
BG = "#1a1b27"
TITLE = "#70a5fd"
TEXT = "#a9b1d6"
ICON = "#bf91f3"
MUTED = "#565f89"
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Sans-Serif"

API = "https://api.github.com/graphql"

# Ícones Octicons de 16px (estrela e fork)
STAR = ("M8 .25a.75.75 0 01.673.418l1.882 3.815 4.21.612a.75.75 0 01.416 1.279l-3.046 2.97.719 "
        "4.192a.75.75 0 01-1.088.791L8 12.347l-3.766 1.98a.75.75 0 01-1.088-.79l.72-4.194L.818 "
        "6.374a.75.75 0 01.416-1.28l4.21-.611L7.327.668A.75.75 0 018 .25z")
FORK = ("M5 3.25a.75.75 0 11-1.5 0 .75.75 0 011.5 0zm0 2.122a2.25 2.25 0 10-1.5 0v.878A2.25 2.25 0 "
        "005.75 8.5h1.5v2.128a2.251 2.251 0 101.5 0V8.5h1.5a2.25 2.25 0 002.25-2.25v-.878a2.25 2.25 0 "
        "10-1.5 0v.878a.75.75 0 01-.75.75h-4.5A.75.75 0 015 6.25v-.878zm3.75 7.378a.75.75 0 11-1.5 0 "
        ".75.75 0 011.5 0zm3-8.75a.75.75 0 100-1.5.75.75 0 000 1.5z")


def graphql(query, token):
    req = urllib.request.Request(
        API,
        data=json.dumps({"query": query}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    if body.get("errors"):
        raise SystemExit(f"Erro da API do GitHub: {body['errors']}")
    return body["data"]


def fetch(user, repos, token):
    pins = "\n".join(
        f'r{i}: repository(owner: "{user}", name: "{name}") {{ ...Repo }}'
        for i, name in enumerate(repos)
    )
    query = f"""
    fragment Repo on Repository {{
      name description stargazerCount forkCount
      primaryLanguage {{ name color }}
    }}
    {{
      user(login: "{user}") {{
        name login
        contributionsCollection {{ totalCommitContributions restrictedContributionsCount }}
        pullRequests {{ totalCount }}
        issues {{ totalCount }}
        repositoriesContributedTo(contributionTypes: [COMMIT, PULL_REQUEST, ISSUE, REPOSITORY]) {{ totalCount }}
        repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {{
          nodes {{
            stargazerCount
            languages(first: 10, orderBy: {{field: SIZE, direction: DESC}}) {{
              edges {{ size node {{ name color }} }}
            }}
          }}
        }}
      }}
      {pins}
    }}
    """
    data = graphql(query, token)
    return data["user"], [data[f"r{i}"] for i in range(len(repos))]


def svg(width, height, body, label):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(label)}">'
        f"<style>text{{font-family:{FONT}}}</style>"
        f'<rect x="0.5" y="0.5" rx="4.5" width="{width - 1}" height="{height - 1}" fill="{BG}"/>'
        f"{body}</svg>"
    )


def wrap(text, limit=52, lines=2):
    words, out, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > limit:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        out.append(cur)
    if len(out) > lines:
        out = out[:lines]
        out[-1] = out[-1][: limit - 3].rstrip() + "..."
    return out


def fmt(n):
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


def stats_card(user):
    c = user["contributionsCollection"]
    rows = [
        ("Total Stars", sum(r["stargazerCount"] for r in user["repositories"]["nodes"])),
        ("Commits (last year)", c["totalCommitContributions"] + c["restrictedContributionsCount"]),
        ("Total PRs", user["pullRequests"]["totalCount"]),
        ("Total Issues", user["issues"]["totalCount"]),
        ("Contributed to", user["repositoriesContributedTo"]["totalCount"]),
    ]
    name = user["name"] or user["login"]
    body = f'<text x="25" y="35" fill="{TITLE}" font-size="18" font-weight="600">{escape(name)}\'s GitHub Stats</text>'
    for i, (label, value) in enumerate(rows):
        y = 70 + i * 25
        body += (
            f'<circle cx="31" cy="{y - 5}" r="5" fill="{ICON}"/>'
            f'<text x="45" y="{y}" fill="{TEXT}" font-size="14" font-weight="600">{label}:</text>'
            f'<text x="230" y="{y}" fill="{TEXT}" font-size="14" font-weight="700">{fmt(value)}</text>'
        )
    return svg(350, 195, body, "GitHub stats")


def langs_card(user, count=6):
    totals, colors = {}, {}
    for repo in user["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            lang = edge["node"]["name"]
            totals[lang] = totals.get(lang, 0) + edge["size"]
            colors[lang] = edge["node"]["color"] or MUTED
    top = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:count]
    total = sum(size for _, size in top) or 1

    body = f'<text x="25" y="35" fill="{TITLE}" font-size="18" font-weight="600">Most Used Languages</text>'
    # Barra única dividida por linguagem (layout "compact")
    body += '<clipPath id="bar"><rect x="25" y="55" width="300" height="8" rx="4"/></clipPath><g clip-path="url(#bar)">'
    x = 25.0
    for lang, size in top:
        w = 300 * size / total
        body += f'<rect x="{x:.2f}" y="55" width="{w:.2f}" height="8" fill="{colors[lang]}"/>'
        x += w
    body += "</g>"
    for i, (lang, size) in enumerate(top):
        cx = 25 + (i % 2) * 165
        cy = 90 + (i // 2) * 25
        body += (
            f'<circle cx="{cx + 5}" cy="{cy - 4}" r="5" fill="{colors[lang]}"/>'
            f'<text x="{cx + 15}" y="{cy}" fill="{TEXT}" font-size="12">'
            f"{escape(lang if len(lang) <= 14 else lang[:13] + '…')} {100 * size / total:.1f}%</text>"
        )
    return svg(350, 165, body, "Top languages")


def pin_card(repo):
    desc = repo["description"] or "No description provided"
    body = (
        f'<path transform="translate(25 22)" fill="{ICON}" d="M2 2.5A2.5 2.5 0 014.5 0h8.75a.75.75 0 '
        f'01.75.75v12.5a.75.75 0 01-.75.75h-2.5a.75.75 0 110-1.5h1.75v-2h-8a1 1 0 00-.714 1.7.75.75 0 '
        f'01-1.072 1.05A2.495 2.495 0 012 11.5v-9zm10.5-1V9h-8c-.356 0-.694.074-1 .208V2.5a1 1 0 '
        f'011-1h8zM5 12.25v3.25a.25.25 0 00.4.2l1.45-1.087a.25.25 0 01.3 0L8.6 15.7a.25.25 0 00.4-.2v-3.25a.25.25 '
        f'0 00-.25-.25h-3.5a.25.25 0 00-.25.25z"/>'
        f'<text x="50" y="35" fill="{TITLE}" font-size="18" font-weight="600">{escape(repo["name"])}</text>'
    )
    for i, line in enumerate(wrap(desc)):
        body += f'<text x="25" y="{65 + i * 18}" fill="{TEXT}" font-size="13">{escape(line)}</text>'

    x, footer = 25, ""
    lang = repo["primaryLanguage"]
    if lang:
        footer += (
            f'<circle cx="{x + 6}" cy="96" r="6" fill="{lang["color"] or MUTED}"/>'
            f'<text x="{x + 17}" y="101" fill="{TEXT}" font-size="12">{escape(lang["name"])}</text>'
        )
        x += 30 + 7 * len(lang["name"])
    footer += (
        f'<path transform="translate({x} 89)" fill="{TEXT}" d="{STAR}"/>'
        f'<text x="{x + 20}" y="101" fill="{TEXT}" font-size="12">{fmt(repo["stargazerCount"])}</text>'
        f'<path transform="translate({x + 55} 89)" fill="{TEXT}" d="{FORK}"/>'
        f'<text x="{x + 75}" y="101" fill="{TEXT}" font-size="12">{fmt(repo["forkCount"])}</text>'
    )
    return svg(400, 120, body + footer, repo["name"])


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    user_login, out_dir, repos = sys.argv[1], sys.argv[2], sys.argv[3:]
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("Defina a variável GITHUB_TOKEN.")

    user, pins = fetch(user_login, repos, token)
    os.makedirs(out_dir, exist_ok=True)

    files = {"stats.svg": stats_card(user), "top-langs.svg": langs_card(user)}
    for name, repo in zip(repos, pins):
        if repo is None:
            print(f"Aviso: repositório {name} não encontrado, card ignorado.")
            continue
        files[f"pin-{name}.svg"] = pin_card(repo)

    for filename, content in files.items():
        with open(os.path.join(out_dir, filename), "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Gerado {filename}")


if __name__ == "__main__":
    main()
