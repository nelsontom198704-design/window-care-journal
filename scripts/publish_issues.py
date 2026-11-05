import os
import re
import html
import urllib.request
import urllib.parse
import json
from pathlib import Path
from datetime import datetime, timezone

import markdown
import bleach
from bs4 import BeautifulSoup

REPOSITORY = os.environ["GH_REPOSITORY"]
TOKEN = os.environ["GH_TOKEN"]

SITE_NAME = "Window Care Journal"
BASE_PATH = "/window-care-journal/"
BASE_URL = (
    f"https://{REPOSITORY.split('/')[0]}.github.io"
    f"{BASE_PATH}"
)

ARTICLES_DIR = Path("articles")
ARTICLES_DIR.mkdir(exist_ok=True)

API = f"https://api.github.com/repos/{REPOSITORY}/issues"

ALLOWED_TAGS = [
    "p", "br", "h2", "h3", "h4", "h5", "h6",
    "strong", "b", "em", "i", "u", "s",
    "ul", "ol", "li", "blockquote", "hr",
    "a", "img", "pre", "code", "div", "span",
    "table", "thead", "tbody", "tr", "th", "td"
]

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title"],
    "img": ["src", "alt", "title"],
    "th": ["colspan", "rowspan"],
    "td": ["colspan", "rowspan"],
}


def get_issues():
    issues = []
    page = 1

    while True:
        params = urllib.parse.urlencode({
            "state": "open",
            "per_page": 100,
            "page": page,
            "sort": "created",
            "direction": "desc"
        })

        request = urllib.request.Request(
            f"{API}?{params}",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "WindowCareJournalPublisher"
            }
        )

        with urllib.request.urlopen(
            request, timeout=30
        ) as response:
            data = json.load(response)

        if not data:
            break

        issues.extend(
            item for item in data
            if "pull_request" not in item
        )

        if len(data) < 100:
            break

        page += 1

    return issues


def clean_html(content):
    rendered = markdown.markdown(
        content or "",
        extensions=["extra", "sane_lists"]
    )

    cleaned = bleach.clean(
        rendered,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=["http", "https"],
        strip=True
    )

    soup = BeautifulSoup(cleaned, "html.parser")

    for link in soup.find_all("a"):
        href = link.get("href", "")
        parsed = urllib.parse.urlsplit(href)

        if parsed.scheme not in ("http", "https"):
            link.unwrap()
            continue

        link["rel"] = "noopener noreferrer"

    for image in soup.find_all("img"):
        src = image.get("src", "")
        parsed = urllib.parse.urlsplit(src)

        if parsed.scheme not in ("http", "https"):
            image.decompose()
            continue

        image["loading"] = "lazy"
        image["alt"] = image.get("alt", "")

    return str(soup)


def page_template(title, content, date, canonical):
    safe_title = html.escape(title)
    safe_date = html.escape(date)
    safe_name = html.escape(SITE_NAME)

    description = html.escape(
        title[:155], quote=True
    )

    year = datetime.now(timezone.utc).year

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index, follow">
<meta name="description" content="{description}">
<link rel="canonical" href="{canonical}">
<title>{safe_title} | {safe_name}</title>
<style>
* {{
  box-sizing: border-box;
}}
body {{
  margin: 0;
  background: #f5f7f5;
  color: #29372f;
  font: 16px/1.8 Arial, sans-serif;
}}
header, footer {{
  padding: 25px 20px;
  text-align: center;
  background: #fff;
}}
header a {{
  color: #315b43;
  font-size: 21px;
  font-weight: bold;
  text-decoration: none;
}}
main {{
  max-width: 850px;
  margin: 45px auto;
  padding: 35px;
  background: #fff;
  border-radius: 12px;
}}
h1, h2, h3 {{
  color: #315b43;
  line-height: 1.4;
}}
h1 {{
  font-size: 32px;
}}
a {{
  color: #315b43;
}}
time {{
  color: #69776d;
  font-size: 14px;
}}
img {{
  display: block;
  max-width: 100%;
  height: auto;
  margin: 20px 0;
  border-radius: 6px;
}}
.article-content {{
  overflow-wrap: anywhere;
}}
.article-content p {{
  margin: 16px 0;
}}
.article-content table {{
  display: block;
  max-width: 100%;
  overflow-x: auto;
  border-collapse: collapse;
}}
.article-content td,
.article-content th {{
  padding: 8px;
  border: 1px solid #ddd;
}}
@media (max-width: 600px) {{
  main {{
    margin: 20px 12px;
    padding: 22px;
  }}
  h1 {{
    font-size: 26px;
  }}
}}
</style>
</head>
<body>
<header>
<a href="{BASE_URL}">{safe_name}</a>
</header>
<main>
<article>
<h1>{safe_title}</h1>
<p><time datetime="{safe_date}">{safe_date}</time></p>
<div class="article-content">
{content}
</div>
</article>
</main>
<footer>&copy; {year} {safe_name}</footer>
</body>
</html>"""


def create_article(issue):
    number = issue["number"]
    title = issue.get("title") or f"Article {number}"
    body = issue.get("body") or ""
    date = (issue.get("created_at") or "")[:10]

    filename = f"issue-{number}.html"
    canonical = f"{BASE_URL}articles/{filename}"

    content = clean_html(body)

    article_html = page_template(
        title, content, date, canonical
    )

    (ARTICLES_DIR / filename).write_text(
        article_html, encoding="utf-8"
    )

    return {
        "title": title,
        "url": f"{BASE_PATH}articles/{filename}",
        "date": date,
        "number": number
    }


def update_homepage(articles):
    path = Path("index.html")

    if path.exists():
        soup = BeautifulSoup(
            path.read_text(encoding="utf-8"),
            "html.parser"
        )

        container = soup.select_one(".article-list")

        if container is not None:
            container.clear()

            for article in articles:
                paragraph = soup.new_tag("p")
                link = soup.new_tag(
                    "a", href=article["url"]
                )
                link.string = article["title"]
                paragraph.append(link)
                container.append(paragraph)

            path.write_text(
                str(soup), encoding="utf-8"
            )
            return

    links = []

    for article in articles:
        links.append(
            f'<li><a href="{html.escape(article["url"], quote=True)}">'
            f'{html.escape(article["title"])}</a> '
            f'<small>({html.escape(article["date"])})</small></li>'
        )

    listing = (
        "<ul>" + "\n".join(links) + "</ul>"
        if links else "<p>No articles published yet.</p>"
    )

    homepage = page_template(
        "Latest Articles",
        listing,
        datetime.now(timezone.utc).date().isoformat(),
        BASE_URL
    )

    path.write_text(homepage, encoding="utf-8")


def main():
    issues = get_issues()

    active_files = {
        f"issue-{issue['number']}.html"
        for issue in issues
    }

    for file in ARTICLES_DIR.glob("issue-*.html"):
        if file.name not in active_files:
            file.unlink()
            print(f"Removed closed article: {file.name}")

    issues.sort(
        key=lambda item: item.get("created_at", ""),
        reverse=True
    )

    articles = []

    for issue in issues:
        articles.append(create_article(issue))

    update_homepage(articles)

    print(f"Published {len(articles)} articles")


if __name__ == "__main__":
    main()
