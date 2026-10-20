# NOTE (29 Sep 2026): recipe photographs are OFF on the public page. Food.com owns them and the
# dataset licence does not cover redistribution. Do not write them into site/ again; the images
# fetched earlier now live in data/interim/recipe-images/ (gitignored, never deployed).
"""Fetch the photograph Food.com shows for each recipe in the demo extract.

Why: the dataset carries no images, and a photograph of a *different* dish beside a real
recipe name would be a fabricated visual claim. The only honest per-recipe image is the one
Food.com itself publishes for that exact recipe id. Rish accepted the terms-of-service risk of
fetching these (D-027); this script fetches only the ~470 recipes the demo can display, at
thumbnail size, once, politely.

Method: GET https://www.food.com/recipe/x-<id> (the site redirects any slug to the canonical
one), read the `og:image` meta, rewrite the CDN transform to a 480x360 crop, download, verify
with PIL, save as site/img/recipes/<id>.jpg. Resume-safe: existing files are skipped.

Writes site/img/recipes/manifest.json with the source page and image URL for every id, and a
`failed` list for anything that could not be fetched, so the page can fall back gracefully.
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "site" / "assets" / "data.json"
OUT = ROOT / "site" / "img" / "recipes"
MANIFEST = OUT / "manifest.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
TRANSFORM = "w_480,h_360,c_fill,q_80"
DELAY_S = 1.2
OG = re.compile(r'<meta\s+(?:name|property)="og:image"\s+content="([^"]+)"', re.I)
LD = re.compile(r'"image"\s*:\s*"(https://img\.sndimg\.com/[^"]+)"')
CDN = re.compile(r"(https://img\.sndimg\.com/food/image/upload/)([^/]*)(/v1/.+)$")


def recipe_ids() -> dict[int, str]:
    d = json.loads(DATA.read_text(encoding="utf-8"))
    out: dict[int, str] = {}
    for p in d["profiles"]:
        for c in p["candidates"]:
            out[int(c["id"])] = c["name"]
    return out


def find_image(html: str) -> str | None:
    m = OG.search(html) or LD.search(html)
    if not m:
        return None
    url = m.group(1).replace("&amp;", "&")
    if "img.sndimg.com" not in url:
        return None
    cm = CDN.match(url)
    return f"{cm.group(1)}{TRANSFORM}{cm.group(3)}" if cm else url


def fetch(session: requests.Session, rid: int) -> tuple[str, str | None, str | None]:
    page = f"https://www.food.com/recipe/x-{rid}"
    r = session.get(page, timeout=40, allow_redirects=True)
    if r.status_code != 200:
        return page, None, f"http {r.status_code}"
    img = find_image(r.text)
    if not img:
        return r.url, None, "no og:image"
    ir = session.get(img, timeout=60)
    if ir.status_code != 200:
        return r.url, img, f"image http {ir.status_code}"
    im = Image.open(io.BytesIO(ir.content))
    im.load()
    im = im.convert("RGB")
    im.save(OUT / f"{rid}.jpg", "JPEG", quality=82, optimize=True, progressive=True)
    return r.url, img, None


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ids = recipe_ids()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {
        "transform": TRANSFORM, "recipes": {}, "failed": {},
    }
    session = requests.Session()
    session.headers["User-Agent"] = UA
    done = 0
    skipped = 0
    for i, (rid, name) in enumerate(sorted(ids.items()), 1):
        key = str(rid)
        if (OUT / f"{rid}.jpg").exists() and key in manifest["recipes"]:
            skipped += 1
            continue
        try:
            page, img, err = fetch(session, rid)
        except Exception as e:  # noqa: BLE001 - one bad recipe must not stop the run
            page, img, err = f"https://www.food.com/recipe/x-{rid}", None, f"{e.__class__.__name__}: {e}"
        if err:
            manifest["failed"][key] = {"name": name, "page": page, "image": img, "error": err}
            print(f"  [{i}/{len(ids)}] {rid} FAILED {err}")
        else:
            manifest["recipes"][key] = {"name": name, "page": page, "image": img, "file": f"{rid}.jpg"}
            manifest["failed"].pop(key, None)
            done += 1
        if i % 25 == 0 or i == len(ids):
            MANIFEST.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
            print(f"[{i}/{len(ids)}] fetched {done}, skipped {skipped}, failed {len(manifest['failed'])}")
        time.sleep(DELAY_S)
    MANIFEST.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    total = sum(f.stat().st_size for f in OUT.glob("*.jpg"))
    print(f"\ndone: {len(manifest['recipes'])} images, {len(manifest['failed'])} failed, "
          f"{total/1e6:.1f} MB in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
