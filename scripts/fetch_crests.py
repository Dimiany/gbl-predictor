"""Download the official team crests and store site-ready copies.

Usage:
    python scripts/fetch_crests.py           # every team in data/crest_sources.csv
    python scripts/fetch_crests.py PAOK AEK  # just these teams

Sources (data/crest_sources.csv) are the league's own team images on esake.gr,
far sharper than FlashScore's 30x30 / 100x100 ones. Some carry a sponsor logo
under the crest: rows with ``crop=sponsor`` go through ``crop_to_crest``, which
keeps the largest blob separated from the rest by fully transparent rows or
columns. ``crop=none`` keeps the image whole (stars above a crest are part of
it; Kolossos' "H" is in its official crest everywhere, so it stays).
Output: src/web/assets/crests/<slug>.webp, CREST_SIZE px square, fitted inside
the circle the site shows crests in. The site
inlines these and falls back to FlashScore for teams without one.
Re-run when a team changes its crest or a new team is promoted.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from PIL import Image

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src import config as cfg  # noqa: E402
from src.web.data import crest_file  # noqa: E402

ALPHA_EMPTY = 8  # alpha at or below this counts as transparent
MIN_GAP_PX = 6  # a sponsor is separated from the crest by at least this much
CIRCLE_FILL = 0.94  # crest reaches 94% of the circle's radius: a hair of white rim


def _bands(mask: list[bool], min_gap: int) -> list[tuple[int, int]]:
    """Runs of True in ``mask``, merging runs split by gaps shorter than min_gap."""
    bands: list[list[int]] = []
    gap = min_gap
    for i, filled in enumerate(mask):
        if filled:
            if bands and gap < min_gap:
                bands[-1][1] = i + 1
            else:
                bands.append([i, i + 1])
            gap = 0
        else:
            gap += 1
    return [(a, b) for a, b in bands]


def crop_to_crest(img: Image.Image) -> Image.Image:
    """Keep the largest block of the image: the crest, without a sponsor logo."""
    img = img.convert("RGBA")
    for _ in range(2):  # a second pass catches a sponsor revealed by the first crop
        filled = np.asarray(img)[:, :, 3] > ALPHA_EMPTY
        top, bottom = max(
            _bands(filled.any(axis=1).tolist(), MIN_GAP_PX), key=lambda b: b[1] - b[0]
        )
        img = img.crop((0, top, img.width, bottom))
        filled = filled[top:bottom]
        left, right = max(
            _bands(filled.any(axis=0).tolist(), MIN_GAP_PX), key=lambda b: b[1] - b[0]
        )
        img = img.crop((left, 0, right, img.height))
    return img


def fit_in_circle(img: Image.Image, size: int, fill: float = CIRCLE_FILL) -> Image.Image:
    """Centre on a transparent ``size`` square, scaled so no opaque pixel falls
    outside the circle the site draws crests in (``border-radius: 50%``).

    Scaling by the farthest opaque pixel from the centre (not the bounding box)
    keeps round crests large while shield corners still fit.
    """
    filled = np.asarray(img)[:, :, 3] > ALPHA_EMPTY
    ys, xs = np.nonzero(filled)
    cy, cx = (img.height - 1) / 2, (img.width - 1) / 2
    reach = float(np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2).max()) + 1
    scale = fill * (size / 2) / reach
    w, h = max(1, round(img.width * scale)), max(1, round(img.height * scale))
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(img.resize((w, h), Image.LANCZOS), ((size - w) // 2, (size - h) // 2))
    return canvas


def main(teams: list[str]) -> None:
    sources = pd.read_csv(cfg.CREST_SOURCES_CSV)
    if teams:
        sources = sources[sources["team"].isin(teams)]
    cfg.CRESTS_DIR.mkdir(parents=True, exist_ok=True)
    for team, url, crop in zip(sources["team"], sources["url"], sources["crop"], strict=True):
        resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
        img = crop_to_crest(img) if crop == "sponsor" else img.crop(img.getbbox())
        crest = fit_in_circle(img, cfg.CREST_SIZE)
        out = crest_file(team)
        crest.save(out, "WEBP", quality=92, method=6)
        print(f"{team:28s} -> {out.name} ({out.stat().st_size // 1024} KB)", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
