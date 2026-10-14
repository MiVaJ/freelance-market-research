"""Сбор данных об услугах с Freeworker."""

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "freeworker.db"
BASE_URL = "https://freeworker.su"

CATEGORIES = {
    "script-programming": "Скрипты, боты, mini apps",
    "ai-development": "Разработка на основе ИИ",
    "moduli": "Модули и плагины",
    "mobile-apps": "Мобильные приложения",
    "website-repair": "Доработка и настройка сайта",
    "crypto": "Крипто и блокчейн",
    "software": "Программы для ПК",
}

MAX_PAGES = 5
CARDS_PER_PAGE = 24


def create_database(conn):
    """Создаёт таблицу, если база новая."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kworks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            title TEXT,
            price TEXT,
            seller TEXT,
            rating TEXT,
            reviews_count TEXT,
            seller_level TEXT,
            category TEXT,
            scraped_at TEXT
        )
        """
    )
    conn.commit()


def parse_price(price_text):
    """Преобразует «от 7 000 ₽» или «2 500 ₽» в число."""
    if not price_text:
        return None
    normalized = price_text.replace("\xa0", " ").strip()
    match = re.search(r"\d[\d\s]*", normalized)
    if not match:
        return None
    try:
        return int(re.sub(r"\s+", "", match.group()))
    except ValueError:
        return None


def parse_level(text):
    """Преобразует текст уровня продавца в число."""
    if not text:
        return None
    text = text.strip().lower()
    if "профессионал" in text:
        return "3"
    if "опытный" in text:
        return "2"
    if "новичок" in text:
        return "1"
    return None


def parse_card(card, category):
    """Достаёт нужные поля из одной карточки услуги."""
    data_id = card.get("data-id")
    if not data_id:
        return None

    title_link = card.select_one("a.multiline-faded")
    href = title_link.get("href") if title_link else None

    if not href or href.startswith("ads/"):
        return None

    title_span = card.select_one("span.first-letter.dib")
    price_div = card.select_one("div.price")
    seller_link = card.select_one("div.cusongsblock-panel__user-name a.dark-link")
    rating_num = card.select_one("li.rating-block__rating-item--number")

    reviews = None
    for span in card.select("span.rating-block__count"):
        tooltip = span.get("data-tooltip-text", "")
        if "просмотр" not in tooltip.lower():
            reviews = span.get_text(strip=True)
            break

    level_text = None
    user_name_block = card.select_one("div.cusongsblock-panel__user-name")
    if user_name_block:
        span = user_name_block.select_one("span")
        if span:
            level_text = span.get_text(strip=True)

    return {
        "url": urljoin(BASE_URL + "/", href),
        "title": title_span.get_text(" ", strip=True) if title_span else None,
        "price": parse_price(
            price_div.get_text(" ", strip=True) if price_div else None
        ),
        "seller": seller_link.get_text(strip=True) if seller_link else None,
        "rating": rating_num.get_text(strip=True) if rating_num else None,
        "reviews_count": reviews,
        "seller_level": parse_level(level_text),
        "category": category,
        "scraped_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def save_kworks(conn, kworks):
    """Сохраняет новые услуги и возвращает число добавленных записей."""
    before = conn.total_changes
    conn.executemany(
        """
        INSERT OR IGNORE INTO kworks (
            url, title, price, seller, rating, reviews_count,
            seller_level, category, scraped_at
        )
        VALUES (
            :url, :title, :price, :seller, :rating, :reviews_count,
            :seller_level, :category, :scraped_at
        )
        """,
        [item for item in kworks if item and item["url"]],
    )
    conn.commit()
    return conn.total_changes - before


def collect_category(page, slug, category):
    """Собирает страницы одной категории, пока есть смысл листать."""
    all_cards = []
    seen_urls = set()

    for page_num in range(1, MAX_PAGES + 1):
        url = (
            f"{BASE_URL}/market/programming/{slug}"
            f"?s=&sq=&sdisplay=table&page={page_num}"
        )
        print(f"\n=== {category} | страница {page_num} ===")

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except PlaywrightTimeoutError:
            print("Страница не загрузилась. Пропускаем.")
            break

        page.wait_for_timeout(1500)

        soup = BeautifulSoup(page.content(), "html.parser")
        cards = soup.select("div.cusongsblock.js-prd-card")
        print(f"Карточек на странице: {len(cards)}")

        if not cards:
            print("Карточек нет. Останавливаемся.")
            break

        parsed = [parse_card(card, category) for card in cards]
        parsed = [item for item in parsed if item]

        new_on_page = 0
        for item in parsed:
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                all_cards.append(item)
                new_on_page += 1

        print(f"  Новых карточек на странице: {new_on_page}")

        if len(cards) < CARDS_PER_PAGE:
            print("  Карточек меньше 24. Это последняя страница.")
            break

        if new_on_page == 0:
            print("  Новых карточек нет. Останавливаемся.")
            break

    print(f"Всего собрано по категории «{category}»: {len(all_cards)}")
    return all_cards


def main():
    conn = sqlite3.connect(DB_PATH)
    create_database(conn)

    total_added = 0
    total_seen = 0

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                for slug, category in CATEGORIES.items():
                    try:
                        kworks = collect_category(page, slug, category)
                    except Exception as error:  # noqa: BLE001
                        print(f"Ошибка в категории «{category}»: {error}")
                        continue

                    total_seen += len(kworks)
                    added = save_kworks(conn, kworks)
                    total_added += added
                    print(
                        f"Новых записей: {added}; " f"дубликатов: {len(kworks) - added}"
                    )
            finally:
                browser.close()
    finally:
        total_in_db = conn.execute("SELECT COUNT(*) FROM kworks").fetchone()[0]
        conn.close()

    print("\nСбор завершён.")
    print(f"Обработано карточек: {total_seen}")
    print(f"Добавлено новых записей: {total_added}")
    print(f"Всего записей в базе: {total_in_db}")
    print(f"База данных: {DB_PATH}")


if __name__ == "__main__":
    main()
