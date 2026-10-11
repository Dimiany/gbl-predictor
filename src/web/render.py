"""HTML rendering: one page per address, plus the shared CSS, JavaScript and data.

Every page, tab and team has its own address (``/standings``,
``/teams/paok/results``) and its own small HTML file with its own title,
description and canonical link, so search engines index each one. The pages
share ``app.css``, ``app.js`` and ``data.js``, which the browser caches.

The JavaScript lives in ``assets/js/*.js``, one file per concern, loaded in
file-name order (``01-core`` → ``90-app``) and concatenated into a single
strict-mode IIFE. No build tool, no CDN. The pages need a web server (Firebase
Hosting, or scripts/serve.py on the desktop): they link the shared files by
absolute path.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path

from src import config as cfg

ASSETS_DIR = Path(__file__).with_name("assets")
JS_DIR = ASSETS_DIR / "js"


def js_modules() -> list[Path]:
    """The JavaScript modules in load order (numeric file-name prefix)."""
    return sorted(JS_DIR.glob("*.js"))


def bundle_js() -> str:
    """Concatenate every module into one IIFE so they share a private scope."""
    parts = [f"// ---- {p.name}\n{p.read_text(encoding='utf-8')}" for p in js_modules()]
    return "(() => {\n'use strict';\n" + "\n".join(parts) + "\n})();\n"


def bundle_css() -> str:
    return (ASSETS_DIR / "app.css").read_text(encoding="utf-8")


def json_payload(data: dict) -> str:
    """Serialise data for data.js.

    ``allow_nan=False`` fails loudly instead of emitting NaN (invalid JSON), and
    escaping ``</`` stops a team name from ever closing a script tag.
    """
    return json.dumps(data, ensure_ascii=False, allow_nan=False).replace("</", "<\\/")


#: Icons served as files next to the pages (build.write_site_files copies them):
#: name in dashboard/ -> file in assets/. favicon.ico is what crawlers ask for.
ICON_FILES = {
    "favicon.svg": "favicon.svg",
    "apple-touch-icon.png": "apple-touch-icon.png",
    "favicon.ico": "tipoff.ico",
}


def icon_links() -> str:
    """Favicon (SVG, every modern browser and Google's results) + touch icon
    (PNG, phone home screens)."""
    return "\n".join(
        [
            '<link rel="icon" type="image/svg+xml" href="/favicon.svg">',
            '<link rel="icon" href="/favicon.ico" sizes="any">',
            '<link rel="apple-touch-icon" href="/apple-touch-icon.png">',
            '<meta name="theme-color" content="#0b1647">',
        ]
    )


def content_security_policy() -> str:
    """CSP for every page: only our own files (app.js, data.js) may run.

    There is no inline script, so no hash to keep in sync. Inline style
    attributes are used by the DOM builders, hence ``'unsafe-inline'`` for styles
    only. Network access is limited to this origin (the local Refresh/contact
    API) and Firestore (the public form).
    """
    return "; ".join(
        [
            "default-src 'none'",
            "script-src 'self'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data:",
            "connect-src 'self' https://firestore.googleapis.com",
            "base-uri 'none'",
            "form-action 'none'",
        ]
    )


# ---------------------------------------------------------------- page addresses

#: Page key (``pages.<key>`` in the JS) -> address. English terms; an English edition
#: of the site will live under /en/ with the same addresses.
PAGE_SLUGS: dict[str, str] = {
    "home": "",
    "predictions": "predictions",
    "standings": "standings",
    "teams": "teams",
    "schedule": "schedule",
    "model": "model",
    "about": "about",
    "contact": "contact",
    "help": "help",
}
#: Tab key -> address per tab group. The first tab lives at the page's own address.
TAB_SLUGS: dict[str, dict[str, str]] = {
    "predictions": {"next": "", "history": "history", "hits": "hall-of-fame", "all": "games"},
    "model": {"performance": "", "metrics": "metrics", "how": "how-it-works"},
    "team": {"overview": "", "results": "results", "schedule": "schedule"},
}
NOT_FOUND_FILE = "404.html"  # Firebase Hosting serves it for any unknown address
NOT_FOUND_PATH = "/404"

#: The main menu, in order. Rendered into every page's HTML (crawlable links) and
#: reused by the JS (header menu, phone menu sheet).
NAV_PAGES: list[tuple[str, str]] = [
    ("home", "Αρχική"),
    ("predictions", "Προβλέψεις"),
    ("standings", "Βαθμολογία"),
    ("teams", "Ομάδες"),
    ("schedule", "Πρόγραμμα"),
    ("model", "Μοντέλο"),
    ("about", "Σχετικά"),
    ("contact", "Επικοινωνία"),
]
PAGE_LABELS: dict[str, str] = {**dict(NAV_PAGES), "help": "Οδηγίες"}
#: Short names of the tabs that have their own address (breadcrumbs).
TAB_LABELS: dict[str, dict[str, str]] = {
    "predictions": {"history": "Ιστορικό", "hits": "Επιτυχίες", "all": "Όλοι οι αγώνες"},
    "model": {"metrics": "Οδηγός δεικτών", "how": "Πώς δουλεύει"},
    "team": {"results": "Αποτελέσματα", "schedule": "Πρόγραμμα"},
}
EN_NAV_PAGES: list[tuple[str, str]] = [
    ("home", "Home"),
    ("predictions", "Predictions"),
    ("standings", "Standings"),
    ("teams", "Teams"),
    ("schedule", "Schedule"),
    ("model", "Model"),
    ("about", "About"),
    ("contact", "Contact"),
]
EN_PAGE_LABELS: dict[str, str] = {**dict(EN_NAV_PAGES), "help": "Help"}
EN_TAB_LABELS: dict[str, dict[str, str]] = {
    "predictions": {"history": "History", "hits": "High-confidence hits", "all": "All games"},
    "model": {"metrics": "Metrics guide", "how": "How it works"},
    "team": {"results": "Results", "schedule": "Schedule"},
}


def slug(name: str) -> str:
    """Team name -> address part: "AS Karditsas Iaponiki" -> "as-karditsas-iaponiki".

    The JS uses the same rule (``slugOf`` in 01-core.js).
    """
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def page_path(page: str, tab: str | None = None, team: str | None = None, lang: str = "el") -> str:
    """Address of a page, optionally under the English ``/en`` prefix."""
    parts = [PAGE_SLUGS["teams"], slug(team)] if team else [PAGE_SLUGS[page]]
    if tab:
        parts.append(TAB_SLUGS["team" if team else page][tab])
    if lang == "en":
        parts.insert(0, "en")
    return "/" + "/".join(p for p in parts if p)


def page_file(path: str) -> str:
    """Address -> file in dashboard/ (Firebase cleanUrls serves x.html at /x)."""
    return "index.html" if path == "/" else path.strip("/") + ".html"


def address_labels(teams: list[str], lang: str = "el") -> dict[str, str]:
    """Address -> short name ("/teams/paok" -> "PAOK"), for breadcrumbs."""
    page_labels = EN_PAGE_LABELS if lang == "en" else PAGE_LABELS
    tab_labels = EN_TAB_LABELS if lang == "en" else TAB_LABELS
    labels = {page_path(k, lang=lang): v for k, v in page_labels.items()}
    for group in ("predictions", "model"):
        labels |= {page_path(group, t, lang=lang): v for t, v in tab_labels[group].items()}
    for team in teams:
        labels[page_path("team", team=team, lang=lang)] = (
            cfg.TEAM_NAMES_EN.get(team, team) if lang == "en" else team
        )
        labels |= {page_path("team", t, team, lang=lang): v for t, v in tab_labels["team"].items()}
    return labels


def breadcrumbs(path: str, labels: dict[str, str], lang: str = "el") -> list[tuple[str, str]]:
    """[(address, name), ...] from the home page down to ``path``; empty for home."""
    home = "/en" if lang == "en" else "/"
    if path == home:
        return []
    parts = path.strip("/").split("/")
    trail = [(home, (EN_PAGE_LABELS if lang == "en" else PAGE_LABELS)["home"])]
    start = 2 if lang == "en" else 1
    for i in range(start, len(parts) + 1):
        sub = "/" + "/".join(parts[:i])
        if sub in labels:
            trail.append((sub, labels[sub]))
    return trail


@dataclass(frozen=True)
class Page:
    path: str
    title: str  # the full <title>
    description: str


def site_pages(data: dict, lang: str = "el") -> list[Page]:
    """Every address the site has, with its title and description: for each
    page's <head>, the sitemap, and the JS (which updates them on navigation).
    The home page comes first."""
    name, tagline = cfg.SITE_NAME, cfg.SITE_TAGLINE
    season = data.get("season", "")
    league = f"Stoiximan Basket League {season}".strip()
    teams = [r["team"] for r in data.get("standings", [])]

    def page(path: str, title: str, description: str) -> Page:
        return Page(path, f"{title.strip()} · {name}", description)

    pages = [
        Page(
            "/",
            f"{name} · {tagline}",
            f"{cfg.SITE_SLOGAN} Προβλέψεις σκορ, πιθανότητες νίκης, βαθμολογία "
            f"και στατιστικά για τη {league}.",
        ),
        page(
            page_path("predictions"),
            "Προβλέψεις αγώνων Basket League",
            "Προβλεπόμενο σκορ και πιθανότητα νίκης για κάθε αγώνα της επόμενης "
            f"αγωνιστικής της {league}, καταγεγραμμένα πριν από το τζάμπολ.",
        ),
        page(
            page_path("predictions", "history"),
            "Ιστορικό προβλέψεων",
            "Κάθε πρόβλεψη του μοντέλου δίπλα στο τελικό αποτέλεσμα, με φίλτρα "
            "ανά σεζόν, ομάδα, αποτέλεσμα και μοντέλο.",
        ),
        page(
            page_path("predictions", "hits"),
            "Επιτυχίες σε προβλέψεις υψηλής πιθανότητας",
            "Αγώνες όπου το μοντέλο εκτίμησε πιθανότητα νίκης 80% και πάνω για το φαβορί και εκείνο κέρδισε.",
        ),
        page(
            page_path("predictions", "all"),
            "Όλοι οι αγώνες: πρόβλεψη και αποτέλεσμα",
            f"Όλοι οι αγώνες της {league} και της προηγούμενης σεζόν, με το τελικό "
            "σκορ και την πρόβλεψη του μοντέλου.",
        ),
        page(
            page_path("standings"),
            f"Βαθμολογία Basket League {season}",
            f"Η βαθμολογία της {league}: νίκες, ήττες, διαφορά πόντων, έδρα, φόρμα "
            "και δείκτης Elo για κάθε ομάδα.",
        ),
        page(
            page_path("teams"),
            f"Ομάδες Basket League {season}",
            f"Οι {len(teams) or 14} ομάδες της {league}: ρεκόρ, φόρμα, Elo, "
            "αποτελέσματα και πρόγραμμα.",
        ),
        page(
            page_path("schedule"),
            f"Πρόγραμμα αγώνων Basket League {season}",
            f"Το πρόγραμμα της {league} ανά ημέρα, μήνα και ομάδα, με τις "
            "προβλέψεις για την επόμενη αγωνιστική.",
        ),
        page(
            page_path("model"),
            "Πόσο εύστοχο είναι το μοντέλο",
            "Η απόδοση του μοντέλου, αξιολογημένη σε αγώνες που δεν είχε δει: "
            "ποσοστό σωστών προβλέψεων, log-loss, Brier και βαθμονόμηση.",
        ),
        page(
            page_path("model", "metrics"),
            "Οδηγός δεικτών",
            "Τι σημαίνει κάθε αριθμός του site, από το Elo ως το log-loss, σε απλά ελληνικά.",
        ),
        page(
            page_path("model", "how"),
            "Πώς δουλεύει το μοντέλο πρόβλεψης",
            "Elo, φόρμα και ρεκόρ: πώς βγαίνει το προβλεπόμενο σκορ και η "
            "πιθανότητα νίκης για κάθε αγώνα.",
        ),
        page(
            page_path("about"),
            f"Σχετικά με το {name}",
            f"Τι είναι το {name}, πώς δουλεύει και γιατί κάθε πρόβλεψη "
            "καταγράφεται πριν από τον αγώνα.",
        ),
        page(
            page_path("contact"),
            "Επικοινωνία",
            f"Γράψε μας για προτάσεις, λάθη ή συνεργασίες με το {name}.",
        ),
        page(
            page_path("help"),
            "Οδηγίες",
            f"Πώς διαβάζεις το {name}: σελίδες, καρτέλες, δείκτες και σύμβολα.",
        ),
    ]
    for team in teams:
        pages += [
            page(
                page_path("team", team=team),
                f"{team}: αποτελέσματα, πρόγραμμα, προβλέψεις",
                f"{team} στη {league}: ρεκόρ, φόρμα, Elo και οι προβλέψεις του "
                "μοντέλου για τους επόμενους αγώνες.",
            ),
            page(
                page_path("team", "results", team),
                f"{team}: αποτελέσματα {season}",
                f"Όλα τα αποτελέσματα της {team} στη {league}, με την πρόβλεψη "
                "του μοντέλου για κάθε αγώνα.",
            ),
            page(
                page_path("team", "schedule", team),
                f"{team}: πρόγραμμα αγώνων {season}",
                f"Οι επόμενοι αγώνες της {team} στη {league}.",
            ),
        ]
    if lang == "en":
        return english_pages(data)
    return pages


def english_pages(data: dict) -> list[Page]:
    """Every English address and its search-facing metadata.

    The browser UI uses the same current data as Greek, while these complete
    English titles and descriptions make each ``/en`` URL independently useful
    to readers and search engines.
    """
    name, season = cfg.SITE_NAME, data.get("season", "")
    league = f"Stoiximan Greek Basketball League {season}".strip()
    teams = [r["team"] for r in data.get("standings", [])]

    def path(page: str, tab: str | None = None, team: str | None = None) -> str:
        return page_path(page, tab, team, lang="en")

    def page(address: str, title: str, description: str) -> Page:
        return Page(address, f"{title} · {name}", description)

    pages = [
        Page(
            "/en",
            f"{name} · Greek Basketball Predictor",
            f"Basketball score predictions, win probabilities, standings and statistics for the {league}.",
        ),
        page(
            path("predictions"),
            "Greek Basketball Predictions",
            f"Predicted scores and win probabilities for the next round of the {league}, recorded before tip-off.",
        ),
        page(
            path("predictions", "history"),
            "Prediction History",
            "Every model prediction alongside the final score, with filters for season, team, outcome and model version.",
        ),
        page(
            path("predictions", "hits"),
            "High-confidence Prediction Hits",
            "Games where the model assigned the favourite an 80% or higher chance of winning and the favourite won.",
        ),
        page(
            path("predictions", "all"),
            "All Games: Predictions and Results",
            f"Every game from the {league} and the previous season, with final scores and model predictions.",
        ),
        page(
            path("standings"),
            f"Greek Basketball Standings {season}",
            f"{league} standings: wins, losses, point difference, home and away record, form and Elo rating.",
        ),
        page(
            path("teams"),
            f"Greek Basketball Teams {season}",
            f"All {len(teams) or 14} teams in the {league}: records, form, Elo ratings, results and fixtures.",
        ),
        page(
            path("schedule"),
            f"Greek Basketball Schedule {season}",
            f"The {league} schedule by day, month and team, including predictions for the next round.",
        ),
        page(
            path("model"),
            "Model Performance",
            "Model performance assessed on games it had not seen: prediction accuracy, log loss, Brier score and calibration.",
        ),
        page(
            path("model", "metrics"),
            "Metrics Guide",
            "A plain-English guide to every number on the site, from Elo to log loss.",
        ),
        page(
            path("model", "how"),
            "How the Prediction Model Works",
            "How Elo, recent form and record produce a predicted score and win probability for every game.",
        ),
        page(
            path("about"),
            f"About {name}",
            f"What {name} is, how it works, and why each prediction is recorded before tip-off.",
        ),
        page(
            path("contact"),
            "Contact",
            f"Contact {name} with suggestions, corrections or partnership enquiries.",
        ),
        page(path("help"), "Help", f"How to use {name}: pages, tabs, metrics and symbols."),
    ]
    for team in teams:
        shown = cfg.TEAM_NAMES_EN.get(team, team)
        pages += [
            page(
                path("team", team=team),
                f"{shown}: Results, Schedule and Predictions",
                f"{shown} in the {league}: record, form, Elo rating and model predictions for upcoming games.",
            ),
            page(
                path("team", "results", team),
                f"{shown}: Results {season}",
                f"All {shown} results in the {league}, with a model prediction for each game.",
            ),
            page(
                path("team", "schedule", team),
                f"{shown}: Schedule {season}",
                f"Upcoming {shown} fixtures in the {league}.",
            ),
        ]
    return pages


def route_table(pages: list[Page], lang: str = "el") -> dict:
    """What the JS router needs: the slugs, and each address's title + description."""
    return {
        "pages": PAGE_SLUGS,
        "tabs": TAB_SLUGS,
        "nav": [list(item) for item in (EN_NAV_PAGES if lang == "en" else NAV_PAGES)],
        "meta": {p.path: [p.title, p.description] for p in pages},
        "prefix": "en" if lang == "en" else "",
    }


def other_language_path(path: str, lang: str) -> str:
    """The same address in the other language: "/standings" <-> "/en/standings", "/" <-> "/en"."""
    if lang == "en":
        return path.removeprefix("/en") or "/"
    return "/en" if path == "/" else "/en" + path


def page_key(path: str) -> str:
    """Which menu entry an address belongs to: "/teams/paok" -> "teams"."""
    parts = path.strip("/").split("/")
    first = (
        parts[1]
        if parts and parts[0] == "en" and len(parts) > 1
        else ("" if parts == ["en"] else parts[0])
    )
    return next((k for k, v in PAGE_SLUGS.items() if v == first), "home")


def static_nav(path: str, lang: str = "el") -> str:
    """The main menu as plain links, so crawlers that don't run JS still find every page."""
    active = page_key(path)
    nav_pages = EN_NAV_PAGES if lang == "en" else NAV_PAGES
    return "".join(
        f'<a href="{page_path(k, lang=lang)}" data-k="{k}"'
        + (' class="active" aria-current="page"' if k == active else "")
        + f">{html.escape(label)}</a>"
        for k, label in nav_pages
    )


def structured_data(page: Page, labels: dict[str, str], lang: str = "el") -> str:
    """schema.org JSON-LD: the site's name for Google's results (home) and the
    breadcrumb trail (every other page). Data only: browsers never execute it,
    so the CSP doesn't need to allow it."""
    url = cfg.SITE_URL
    if page.path == "/":
        data = {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "WebSite",
                    "@id": f"{url}/#website",
                    "name": cfg.SITE_NAME,
                    "alternateName": f"{cfg.SITE_NAME} · {cfg.SITE_TAGLINE}",
                    "url": f"{url}/",
                    "inLanguage": lang,
                    "description": page.description,
                    "publisher": {"@id": f"{url}/#organization"},
                },
                {
                    "@type": "Organization",
                    "@id": f"{url}/#organization",
                    "name": cfg.SITE_NAME,
                    "url": f"{url}/",
                    "logo": f"{url}/apple-touch-icon.png",
                },
            ],
        }
    else:
        data = {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": i,
                    "name": name,
                    "item": url + ("/" if path == "/" else path),
                }
                for i, (path, name) in enumerate(breadcrumbs(page.path, labels, lang), start=1)
            ],
        }
    return f'<script type="application/ld+json">{json_payload(data)}</script>'


def share_meta(page: Page, mode: str | None, lang: str = "el") -> str:
    """Open Graph / Twitter card tags (link previews in Viber, Messenger, Facebook,
    X, Slack...) and the canonical address (search engines index tipoff.gr, not
    the *.web.app aliases). Search Console is verified by a DNS TXT record.

    Previews need an absolute image URL, so the card always points at SITE_URL.
    """
    name, url = cfg.SITE_NAME, cfg.SITE_URL
    title = html.escape(page.title, quote=True)
    desc = html.escape(page.description, quote=True)
    address = url + ("/" if page.path == "/" else page.path)
    image = f"{url}/{cfg.SHARE_CARD_FILE}"
    locale = "en_US" if lang == "en" else "el_GR"
    tags = [
        '<meta property="og:type" content="website">',
        f'<meta property="og:site_name" content="{html.escape(name, quote=True)}">',
        f'<meta property="og:title" content="{title}">',
        f'<meta property="og:description" content="{desc}">',
        f'<meta property="og:url" content="{address}">',
        f'<meta property="og:image" content="{image}">',
        '<meta property="og:image:width" content="1200">',
        '<meta property="og:image:height" content="630">',
        f'<meta property="og:image:alt" content="{html.escape(name, quote=True)}">',
        f'<meta property="og:locale" content="{locale}">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{title}">',
        f'<meta name="twitter:description" content="{desc}">',
        f'<meta name="twitter:image" content="{image}">',
    ]
    if mode == "live":
        tags.append(f'<link rel="canonical" href="{address}">')
        # Each page and its translation point at each other (hreflang); Greek is the default.
        greek = page.path if lang == "el" else other_language_path(page.path, lang)
        english = other_language_path(greek, "el")
        for code, path in (("el", greek), ("en", english), ("x-default", greek)):
            href = url + ("/" if path == "/" else path)
            tags.append(f'<link rel="alternate" hreflang="{code}" href="{href}">')
    return "\n".join(tags)


def render_page(
    data: dict,
    page: Page,
    noindex: bool = False,
    labels: dict[str, str] | None = None,
    lang: str = "el",
) -> str:
    """One page: its own <head> (title, description, canonical, JSON-LD), the shared
    shell with the menu as plain links, and the shared files. The JS then renders
    the content for the address.

    ``<main>`` starts with the page's heading and description, so crawlers that
    don't run JS still read what the page is about. It is invisible (no flash
    before the JS replaces it) but in the HTML.
    """
    mode = data.get("site", {}).get("mode")
    # Preview links are for checking a change, not for search engines.
    noindex = noindex or mode == "preview"
    robots = '\n<meta name="robots" content="noindex, nofollow">' if noindex else ""
    name, tagline = cfg.SITE_NAME, cfg.SITE_TAGLINE
    if labels is None:
        labels = address_labels([r["team"] for r in data.get("standings", [])], lang)
    found = page.path != NOT_FOUND_PATH
    heading = html.escape(page.title.removesuffix(f" · {name}"))
    intro = f'<div class="ssr"><h1>{heading}</h1><p>{html.escape(page.description)}</p></div>'
    language_url = other_language_path(page.path, lang)
    other = "el" if lang == "en" else "en"

    def t(el: str, en: str) -> str:
        """Shell text in the page's language (the JS has the same T())."""
        return en if lang == "en" else el

    return f"""<!doctype html>
<html lang="{lang}" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark light">
<meta http-equiv="Content-Security-Policy" content="{content_security_policy()}">{robots}
<meta name="description" content="{html.escape(page.description, quote=True)}">
<title>{html.escape(page.title)}</title>
{icon_links()}
{share_meta(page, mode, lang) if found else ""}
{structured_data(page, labels, lang) if found else ""}
<link rel="stylesheet" href="/app.css">
<script src="/{"data-en.js" if lang == "en" else "data.js"}" defer></script>
<script src="/app.js" defer></script>
</head>
<body>
<div class="viz-root">
  <header class="site-head">
    <a class="brand" href="{page_path("home", lang=lang)}" aria-label="{name}, {t("αρχική", "home")}"><span class="brand-badge" aria-hidden="true"><img src="/favicon.svg" alt=""></span><span class="brand-text"><b>{name}</b><small>{tagline}</small></span></a>
    <nav id="nav" aria-label="{t("Κύρια πλοήγηση", "Main navigation")}">{static_nav(page.path, lang)}</nav>
    <div class="head-tools">
      <a class="lang-switch" href="{language_url}" hreflang="{other}" lang="{other}" aria-label="{t("English", "Ελληνικά")}" title="{t("English", "Ελληνικά")}">{t("EN", "ΕΛ")}</a>
      <button id="refresh" class="btn btn-primary" type="button" title="{t("Φέρνει νέα αποτελέσματα και ξαναβγάζει τις προβλέψεις", "Fetches new results and makes the predictions again")}"><span class="spin" aria-hidden="true">⟳</span> {t("Ανανέωση", "Refresh")}</button>
      <label class="focus-pick"><span>{t("Η ομάδα μου", "My team")}</span><select id="focus" aria-label="{t("Η ομάδα μου", "My team")}"></select></label>
      <a class="icon-btn" href="{page_path("help", lang=lang)}" aria-label="{t("Οδηγίες", "Help")}" title="{t("Οδηγίες", "Help")}">?</a>
      <button id="theme" class="icon-btn" type="button" aria-label="{t("Αλλαγή θέματος", "Change theme")}" title="{t("Σκοτεινό / φωτεινό", "Dark / light")}">◐</button>
    </div>
    <div class="scroll-progress" id="scroll-progress" aria-hidden="true"></div>
  </header>
  <main id="app" tabindex="-1">{intro if found else ""}</main>
  <footer class="site-foot" id="foot"></footer>
  <!-- Overlays stay inside .viz-root: the theme tokens (colours, fonts) live there. -->
  <button class="to-top" id="to-top" type="button" aria-label="{t("Πάνω", "Back to top")}">↑</button>
  <div id="tip" class="tip" role="tooltip" hidden></div>
  <div id="toast" class="toast" role="status" aria-live="polite" hidden></div>
</div>
</body>
</html>"""


def render_html(data: dict) -> str:
    """The home page (index.html)."""
    return render_page(data, site_pages(data)[0])


def render_site(data: dict) -> dict[str, str]:
    """Every generated file of the site: name in dashboard/ -> content."""
    pages = site_pages(data)
    en_pages = site_pages(data, lang="en")
    labels = address_labels([r["team"] for r in data.get("standings", [])])
    en_labels = address_labels([r["team"] for r in data.get("standings", [])], lang="en")
    payload = json_payload({**data, "lang": "el", "routes": route_table(pages)})
    en_brand = {**data.get("brand", {}), "slogan": cfg.SITE_SLOGAN_EN}
    en_payload = json_payload(
        {
            **data,
            "lang": "en",
            "brand": en_brand,
            "team_names": cfg.TEAM_NAMES_EN,
            "routes": route_table(en_pages, lang="en"),
        }
    )
    not_found = Page(NOT_FOUND_PATH, f"Η σελίδα δεν βρέθηκε · {cfg.SITE_NAME}", "")
    files = {
        "app.css": bundle_css(),
        "app.js": bundle_js(),
        "data.js": f"window.TIPOFF_DATA = {payload};\n",
        "data-en.js": f"window.TIPOFF_DATA = {en_payload};\n",
        NOT_FOUND_FILE: render_page(data, not_found, noindex=True, labels=labels),
    }
    files.update({page_file(p.path): render_page(data, p, labels=labels) for p in pages})
    files.update(
        {page_file(p.path): render_page(data, p, labels=en_labels, lang="en") for p in en_pages}
    )
    return files
