"""Printable PDF of the week calendar (itinerary.pdf).

Prints the Schedule tab's calendar (ui.calendar.calendar_html(sched, print_view=True)) on one
landscape Letter page, scaled to fit, with Playwright's Chromium (which the scraper already needs).
"""
from datetime import datetime
from functools import lru_cache

PAGE_W, PAGE_H, MARGIN = 11, 8.5, 0.35  # inches
WIDTH = 1300  # CSS px to lay the calendar out at before scaling

FOOTER = ('<div style="width:100%; font:7px -apple-system, system-ui, sans-serif; color:#6b7280; padding:0 0.35in; display:flex; '
          'justify-content:space-between;"><span>INFORMS 2026 itinerary &middot; San Francisco time</span>'
          '<span>Built {built}</span></div>')


@lru_cache(maxsize=4)
def calendar_pdf(cal_html):
    """Return PDF bytes for a calendar_html() fragment (cached, so repeat downloads are instant)."""
    from playwright.sync_api import sync_playwright

    page_html = f'<!doctype html><html><head><meta charset="utf-8"></head><body>{cal_html}</body></html>'
    built = datetime.now().strftime("%b %d, %I:%M %p").replace(" 0", " ")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": WIDTH, "height": 800})
            page.set_content(page_html, wait_until="load")
            h = page.evaluate("document.body.scrollHeight")
            avail_w, avail_h = (PAGE_W - 2 * MARGIN) * 96, (PAGE_H - 2 * MARGIN - 0.15) * 96  # 96 CSS px/in
            scale = max(0.1, min(avail_w / WIDTH, avail_h / h, 1.0))
            return page.pdf(width=f"{PAGE_W}in", height=f"{PAGE_H}in", scale=scale, print_background=True,
                            display_header_footer=True, header_template="<span></span>",
                            footer_template=FOOTER.format(built=built), page_ranges="1",
                            margin={k: f"{MARGIN}in" for k in ("top", "left", "right")} | {"bottom": f"{MARGIN + 0.15}in"})
        finally:
            browser.close()
