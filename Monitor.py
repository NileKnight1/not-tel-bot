import os
import re
import requests
from bs4 import BeautifulSoup

# ---- EDIT THIS PART ----
AMAZON_ASIN = "B0GSW36PDX"          # from your amazon.eg link
QARENLY_QUERY = "samsung a57"        # search keyword on qarenly.com
MODEL_FILTER = "a57"                 # title must contain this (skips cases/accessories)
MIN_PRICE = 15000                    # ignore anything cheaper than this (EGP)
PAGES = 5                            # Qarenly pages to scan (10 results each)
SHOW = 10                            # how many cheapest to show
# ------------------------

PARSE_BASE = "https://api.parse.bot/scraper/6b1d4645-746f-42aa-a5ac-bf5f861d41f6"
PARSE_KEY = os.environ["PARSE_API_KEY"]
TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
UA = {"User-Agent": "Mozilla/5.0"}

COLOR_RE = re.compile(
    r"(awesome\s+\w+|ice\s*blue|icy\s*blue|navy|gray|grey|black|white|silver|"
    r"lilac|lavender|green|blue|pink|violet|purple|gold|mint|lime|red|yellow|cream)",
    re.I,
)


def send(text):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": text[:4000]},
        timeout=20,
    )


def amazon():
    r = requests.get(
        f"{PARSE_BASE}/get_product_details",
        params={"asin": AMAZON_ASIN},
        headers={"X-API-Key": PARSE_KEY},
        timeout=40,
    )
    r.raise_for_status()
    d = r.json().get("data", {})
    price = d.get("price")
    title = (d.get("title") or AMAZON_ASIN)[:70]
    if price is None:
        return f"Amazon: no price found for {title} (maybe out of stock)"
    return f"Amazon: {float(price):,.0f} EGP - {title}"


def parse_page(html):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for h in soup.find_all("h2"):
        card = h
        for _ in range(6):  # climb until the container holds a price and one title
            card = card.parent
            if card is None:
                break
            if len(card.find_all("h2")) > 1:
                card = None
                break
            if re.search(r"[\d,]+\s*EGP", card.get_text(" ", strip=True)):
                break
        if card is None:
            continue
        text = card.get_text(" ", strip=True)
        m = re.search(r"([\d,]+)\s*EGP", text)
        if not m:
            continue
        price = float(m.group(1).replace(",", ""))
        title = h.get_text(strip=True)
        # store name: taken from the product link, e.g. /en/technology_valley/...
        store = "?"
        a = card.find("a", href=re.compile(r"^(https://qarenly\.com)?/en/[^/]+/[^/]+"))
        if a:
            slug = re.sub(r"^(https://qarenly\.com)?/en/", "", a["href"]).split("/")[0]
            store = slug.replace("_", " ").replace("-", " ").title()
        cm = COLOR_RE.search(title)
        color = cm.group(1).title() if cm else "-"
        items.append((price, store, color, title))
    return items


def qarenly():
    all_items = []
    for page in range(1, PAGES + 1):
        html = requests.get(
            "https://qarenly.com/en",
            params={"searchKeyword": QARENLY_QUERY, "page": page},
            headers=UA,
            timeout=30,
        ).text
        all_items += parse_page(html)
    seen, rows = set(), []
    for price, store, color, title in sorted(all_items):
        if price < MIN_PRICE or MODEL_FILTER not in title.lower():
            continue
        key = (price, store, title)
        if key in seen:
            continue
        seen.add(key)
        rows.append(f"{price:,.0f} EGP | {store} | {color}")
    if not rows:
        return "Qarenly: nothing parsed (page layout may have changed)"
    return "Qarenly cheapest:\n" + "\n".join(rows[:SHOW])


lines = []
for fn in (amazon, qarenly):
    try:
        lines.append(fn())
    except Exception as e:
        lines.append(f"{fn.__name__}: error ({e})")

send("\n\n".join(lines))
