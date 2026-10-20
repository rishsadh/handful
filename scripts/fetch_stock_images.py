"""Fetch Creative-Commons ambience photographs for the project page from Openverse.

These are ATMOSPHERE only: a hero, a section divider, an illustration of each preparation-time
band. They are never shown beside a specific recipe as if they depicted it (D-027). Per-recipe
photographs come from scripts/fetch_recipe_images.py instead.

Openverse is keyless and returns only openly licensed images. Only `by` and `cc0` licences are
accepted so the page can carry a clean attribution block. Three candidates are saved per role;
a human picks one and deletes the rest, because a search API cannot judge whether a photo is
actually usable.

Writes site/img/stock/<role>-<n>.jpg and site/img/stock/manifest.json.
"""
from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "img" / "stock"
UA = "handful-research-demo/1.0 (academic project; contact via repository)"
API = "https://api.openverse.org/v1/images/"
MAX_W = 1600
CANDIDATES = 3

# Several queries per role, tried in order until enough candidates are found. The first
# run used one narrow query per role with a 1000px floor and a wide-only filter and came
# back empty for five of eight roles.
ROLES = {
    "hero": ["dinner table food overhead", "family dinner table dishes", "home cooking table spread", "thanksgiving table food"],
    "menu": ["restaurant menu board", "chalkboard menu cafe", "diner menu", "menu card restaurant"],
    "band-quick": ["avocado toast plate breakfast", "toast breakfast plate"],
    "band-fast": ["stir fry wok vegetables", "pasta bowl dinner"],
    "band-moderate": ["roast vegetables", "roasted vegetables pan", "baked casserole dish", "lasagna dish"],
    "band-long": ["beef stew pot slow cooked", "stew pot", "braised meat pot", "sourdough bread loaf"],
    "notebook": ["recipe notebook handwritten", "handwritten recipe card", "recipe book open kitchen", "cookbook open page"],
    "future": ["empty plate fork knife", "empty white plate table", "place setting empty plate", "dinner plate cutlery"],
}


def search(q: str) -> list[dict]:
    r = requests.get(
        API,
        params={
            "q": q,
            "license": "by,cc0",
            "license_type": "commercial",
            "page_size": 20,
        },
        headers={"User-Agent": UA},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("results", [])


def fetch_image(url: str) -> Image.Image | None:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
        r.raise_for_status()
        im = Image.open(io.BytesIO(r.content))
        im.load()
        return im.convert("RGB")
    except Exception as e:  # noqa: BLE001 - a bad image is skipped, not fatal
        print(f"    skip ({e.__class__.__name__}): {url[:80]}")
        return None


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    # Merge with what is already recorded: an earlier version rebuilt the manifest from
    # scratch and silently dropped the attribution for every role it skipped.
    mpath = OUT / "manifest.json"
    manifest: dict[str, list[dict]] = (
        json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {}
    )
    for role, queries in ROLES.items():
        # Resume-safe: a role with candidates on disk AND in the manifest is left alone.
        existing = sorted(OUT.glob(f"{role}-*.jpg"))
        if existing and manifest.get(role):
            print(f"[{role}] keeping {len(existing)} existing candidate(s)")
            continue
        for f in existing:
            f.unlink()  # on disk but unrecorded: refetch so attribution is complete
        kept: list[dict] = []
        results: list[dict] = []
        for q in queries:
            print(f"[{role}] {q}")
            results = search(q)
            if results:
                break
            time.sleep(0.6)
        for res in results:
            if len(kept) >= CANDIDATES:
                break
            w, h = res.get("width") or 0, res.get("height") or 0
            if w < 800 or h < 500 or h > w * 1.1:
                continue
            im = fetch_image(res["url"])
            if im is None:
                continue
            if im.width > MAX_W:
                im = im.resize((MAX_W, round(im.height * MAX_W / im.width)), Image.LANCZOS)
            n = len(kept) + 1
            path = OUT / f"{role}-{n}.jpg"
            im.save(path, "JPEG", quality=82, optimize=True, progressive=True)
            kept.append(
                {
                    "file": path.name,
                    "role": role,
                    "title": res.get("title"),
                    "creator": res.get("creator"),
                    "creator_url": res.get("creator_url"),
                    "license": res.get("license"),
                    "license_version": res.get("license_version"),
                    "license_url": res.get("license_url"),
                    "source": res.get("foreign_landing_url"),
                    "original_url": res.get("url"),
                    "width": im.width,
                    "height": im.height,
                    "bytes": path.stat().st_size,
                }
            )
            print(f"    saved {path.name}  {im.width}x{im.height}  {res.get('license')} "
                  f"by {res.get('creator')}")
            time.sleep(0.5)
        manifest[role] = kept
        time.sleep(1.0)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    total = sum(len(v) for v in manifest.values())
    print(f"\n{total} candidate images written to {OUT}")
    print("Next: view each role's candidates, keep one, delete the others, then prune manifest.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
