import os
import re
import requests
from bs4 import BeautifulSoup

# ============================================================
# SETTINGS
# ============================================================

AMAZON_ASIN = "B0GSW36PDX"

QARENLY_QUERY = "samsung a57"
MODEL_FILTER = "a57"

MIN_PRICE = 15000
PAGES = 5
SHOW = 10

# ============================================================
# API / TELEGRAM
# ============================================================

PARSE_BASE = "https://api.parse.bot/scraper/6b1d4645-746f-42aa-a5ac-bf5f861d41f6"

PARSE_KEY = os.environ["PARSE_API_KEY"]
TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    )
}

# ============================================================
# COLOR DETECTION
# ============================================================

COLOR_RE = re.compile(
    r"(awesome\s+\w+|ice\s*blue|icy\s*blue|navy|gray|grey|black|white|silver|"
    r"lilac|lavender|green|blue|pink|violet|purple|gold|mint|lime|red|yellow|cream)",
    re.I,
)

# ============================================================
# TELEGRAM
# ============================================================

def send(text):
    response = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": text[:4000],
        },
        timeout=20,
    )

    response.raise_for_status()


# ============================================================
# AMAZON
# ============================================================

def amazon():
    response = requests.get(
        f"{PARSE_BASE}/get_product_details",
        params={
            "asin": AMAZON_ASIN
        },
        headers={
            "X-API-Key": PARSE_KEY
        },
        timeout=40,
    )

    response.raise_for_status()

    data = response.json().get("data", {})

    price = data.get("price")
    title = (data.get("title") or AMAZON_ASIN).strip()

    if price is None:
        return (
            f"Amazon: no price found for {title[:70]} "
            f"(maybe out of stock)"
        )

    return (
        f"Amazon: {float(price):,.0f} EGP - "
        f"{title[:70]}"
    )


# ============================================================
# QARENLY STORE NAME
# ============================================================

def get_store(card):
    """
    Qarenly product URLs normally look like:

    /en/technology_valley/product-name

    We extract the first part after /en/ as the store name.
    """

    ignored_slugs = {
        "search",
        "product",
        "products",
        "technology",
        "phones",
        "mobile",
        "categories",
    }

    for a in card.find_all("a", href=True):

        href = a["href"].strip()

        match = re.match(
            r"^(?:https://qarenly\.com)?/en/([^/?#]+)/",
            href,
            re.I,
        )

        if not match:
            continue

        slug = match.group(1).strip()

        if slug.lower() in ignored_slugs:
            continue

        store = slug.replace("_", " ").replace("-", " ").strip()

        if store:
            return store.title()

    return "?"


# ============================================================
# QARENLY PAGE PARSER
# ============================================================

def parse_page(html):
    soup = BeautifulSoup(html, "html.parser")

    items = []

    for h in soup.find_all("h2"):

        card = h

        # Try to climb to the product card
        for _ in range(6):

            card = card.parent

            if card is None:
                break

            # Don't accidentally combine multiple products
            if len(card.find_all("h2")) > 1:
                card = None
                break

            card_text = card.get_text(" ", strip=True)

            if re.search(r"[\d,]+\s*EGP", card_text):
                break

        if card is None:
            continue

        text = card.get_text(" ", strip=True)

        # ----------------------------------------------------
        # PRICE
        # ----------------------------------------------------

        price_match = re.search(
            r"([\d,]+)\s*EGP",
            text,
            re.I,
        )

        if not price_match:
            continue

        price = float(
            price_match.group(1).replace(",", "")
        )

        # ----------------------------------------------------
        # TITLE
        # ----------------------------------------------------

        title = h.get_text(" ", strip=True)

        # ----------------------------------------------------
        # STORE
        # ----------------------------------------------------

        store = get_store(card)

        # ----------------------------------------------------
        # COLOR
        # ----------------------------------------------------

        color_match = COLOR_RE.search(title)

        if color_match:
            color = color_match.group(1).title()
        else:
            color = "-"

        items.append(
            (
                price,
                store,
                color,
                title,
            )
        )

    return items


# ============================================================
# QARENLY SEARCH
# ============================================================

def qarenly():
    all_items = []

    for page in range(1, PAGES + 1):

        response = requests.get(
            "https://qarenly.com/en",
            params={
                "searchKeyword": QARENLY_QUERY,
                "page": page,
            },
            headers=UA,
            timeout=30,
        )

        response.raise_for_status()

        all_items.extend(
            parse_page(response.text)
        )

    # --------------------------------------------------------
    # FILTER + DEDUPLICATE
    # --------------------------------------------------------

    seen = set()
    rows = []

    for price, store, color, title in sorted(all_items):

        # Minimum price
        if price < MIN_PRICE:
            continue

        # Must contain A57
        if MODEL_FILTER.lower() not in title.lower():
            continue

        key = (
            price,
            store,
            color,
            title,
        )

        if key in seen:
            continue

        seen.add(key)

        rows.append(
            f"{price:,.0f} EGP | {store} | {color}"
        )

    if not rows:
        return (
            "Qarenly: nothing parsed "
            "(page layout may have changed)"
        )

    return (
        "Qarenly cheapest:\n"
        + "\n".join(rows[:SHOW])
    )


# ============================================================
# MAIN
# ============================================================

def main():

    lines = []

    # Amazon
    try:
        lines.append(amazon())

    except Exception as e:
        lines.append(
            f"amazon: error ({e})"
        )

    # Qarenly
    try:
        lines.append(qarenly())

    except Exception as e:
        lines.append(
            f"qarenly: error ({e})"
        )

    send("\n\n".join(lines))


if __name__ == "__main__":
    main()
