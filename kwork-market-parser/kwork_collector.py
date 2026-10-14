"""Сбор данных об услугах с Kwork."""

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "kwork.db"
BASE_URL = "https://kwork.ru"

CATEGORIES = {
    "parsery": "Парсеры",
    "chat-boty": "Чат-боты",
    "skripty": "Скрипты",
    "telegram-mini-apps": "Telegram Mini Apps",
    "ii-agenty": "ИИ-агенты",
    "ii-boty": "ИИ-боты",
}

CLICKS = 1

JS_KWORK_COUNT = (
    "(oldCount) => "
    "document.querySelectorAll('div.kwork-card-item').length > oldCount"
)


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


def parse_kwork_card(card, category):
    """Достаёт нужные поля из одной карточки услуги."""
    title_link = card.select_one("p.kwork-card-item__title a")
    title_span = card.select_one("p.kwork-card-item__title span.force-font")
    price = card.select_one("div.kwork-cards-price span")
    seller = card.select_one("div.kwork-card-item__user-link-wrap a")
    rating = card.select_one("span.kwork-card-item__rating-number")
    reviews = card.select_one("span.kwork-card-item__rating-count")
    level_img = card.select_one("span.kwork-card-item__user-level img")

    level = None
    if level_img:
        image_url = level_img.get("src", "")
        for number in ("3", "2", "1"):
            if f"seller-level-{number}" in image_url:
                level = number
                break

    href = title_link.get("href") if title_link else None

    return {
        "url": urljoin(BASE_URL + "/", href) if href else None,
        "title": title_span.get_text(" ", strip=True)
        if title_span
        else (title_link.get_text(" ", strip=True) if title_link else None),
        "price": price.get_text(" ", strip=True) if price else None,
        "seller": seller.get_text(" ", strip=True) if seller else None,
        "rating": rating.get_text(" ", strip=True) if rating else None,
        "reviews_count": reviews.get_text(" ", strip=True) if reviews else None,
        "seller_level": level,
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
        [item for item in kworks if item["url"]],
    )
    conn.commit()
    return conn.total_changes - before


def collect_category(page, slug, category):
    """Собирает страницы одной категории, кликая «Показать ещё»."""
    url = f"{BASE_URL}/categories/script-programming/{slug}"
    print(f"\n=== {category} ===")
    page.goto(url, wait_until="domcontentloaded", timeout=60000)

    try:
        page.locator("div.kwork-card-item").first.wait_for(timeout=15000)
    except PlaywrightTimeoutError:
        print("Карточки не появились. Возможно, сайт изменился.")
        return []

    for click_number in range(CLICKS):
        button = page.get_by_role(
            "button", name=re.compile(r"Показать\s+ещ[её]", re.IGNORECASE)
        ).first

        try:
            if not button.is_visible():
                break

            old_count = page.locator("div.kwork-card-item").count()
            button.click(timeout=5000)

            try:
                page.wait_for_function(
                    JS_KWORK_COUNT,
                    arg=old_count,
                    timeout=10000,
                )
            except PlaywrightTimeoutError:
                print(f"Новые карточки после клика {click_number + 1} не появились.")
                break

            print(f"Подгрузка {click_number + 1}/{CLICKS} выполнена.")
        except PlaywrightTimeoutError:
            print(
                "Не удалось нажать «Показать ещё». "
                "Продолжаю с уже загруженными карточками."
            )
            break

    soup = BeautifulSoup(page.content(), "html.parser")
    cards = soup.select("div.kwork-card-item")
    print(f"Карточек на странице: {len(cards)}")
    return [parse_kwork_card(card, category) for card in cards]


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
                        print(f"Не удалось обработать категорию «{category}»: {error}")
                        continue

                    total_seen += len(kworks)
                    added = save_kworks(conn, kworks)
                    total_added += added
                    print(
                        f"Новых записей: {added}; "
                        f"уже были в базе: {len(kworks) - added}"
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
