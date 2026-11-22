"""Render the Wisp FAQ pictures in ASSETS/faq from DOCS/wisp_faq.html.

One banner picture per question: the page's title and opening line first,
then each member section's questions, its heading on the first one. The
"For staff" section is left out. Pictures are named
``{NN}_{section}_{k}.png`` in posting order, matching ``cogs.faq.FAQ_SECTIONS``.

Run from the repo with the system Python that has Playwright::

    python tools/render_faq.py

Every old picture in ASSETS/faq is replaced; nothing else is touched.
"""

from pathlib import Path

from playwright.sync_api import Locator, Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "DOCS" / "wisp_faq.html"
OUT = ROOT / "ASSETS" / "faq"

# CSS pixels; the pictures are twice as big, 1440 pixels wide.
WIDTH = 720
SCALE = 2
PAD = 14

# (file stem, section id in the page), in posting order.
SECTIONS: tuple[tuple[str, str], ...] = (
    ("01_basics", "basics"),
    ("02_feeding", "feeding"),
    ("03_vault", "vault"),
    ("04_lunchbox", "lunchbox"),
    ("05_bond", "bond"),
    ("06_growing", "growing"),
    ("07_chores", "chores"),
    ("08_talking", "talking"),
    ("09_games", "games"),
    ("10_ending", "ending"),
    ("11_fair", "fair"),
)


def _shoot(page: Page, parts: list[Locator], path: Path) -> None:
    """Save the full-width strip of the page that holds every one of `parts`."""
    boxes = [box for part in parts if (box := part.bounding_box()) is not None]
    if len(boxes) != len(parts):
        raise RuntimeError(f"{path.name}: a part of the picture is not on the page")
    top = min(box["y"] for box in boxes) - PAD
    bottom = max(box["y"] + box["height"] for box in boxes) + PAD
    page.screenshot(
        path=str(path),
        clip={"x": 0, "y": top, "width": WIDTH, "height": bottom - top},
        full_page=True,
    )


def main() -> None:
    """Replace every FAQ picture with a fresh one from the page."""
    for old in OUT.glob("*.png"):
        old.unlink()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(
            viewport={"width": WIDTH, "height": 900},
            device_scale_factor=SCALE,
            color_scheme="dark",
        )
        page.goto(PAGE.as_uri(), wait_until="networkidle")
        page.evaluate("document.fonts.ready")
        header = page.locator("main > header")
        _shoot(
            page,
            [header.locator("h1"), header.locator(".lede")],
            OUT / "00_how_wisp_works_1.png",
        )
        for stem, section_id in SECTIONS:
            section = page.locator(f"section#{section_id}")
            questions = section.locator(".qa")
            for index in range(questions.count()):
                parts = [questions.nth(index)]
                if index == 0:
                    parts.insert(0, section.locator("h2"))
                _shoot(page, parts, OUT / f"{stem}_{index + 1}.png")
        browser.close()
    print(f"{len(list(OUT.glob('*.png')))} pictures in {OUT}")


if __name__ == "__main__":
    main()
