"""Анализ цен на услуги Kwork."""

import csv
import re
import sqlite3
import statistics
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "kwork.db"
OUTPUT_DIR = BASE_DIR / "output"


def parse_price(price_text):
    """Преобразует цену вида «5 000 ₽» в число."""
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


def get_category_stats(items):
    """Считает статистику и определяет выбросы для одной категории."""
    prices = [item["price"] for item in items]
    if len(prices) < 4:
        return None

    q1, _, q3 = statistics.quantiles(sorted(prices), n=4)
    iqr = q3 - q1
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr

    clean_items = [
        item for item in items if lower_bound <= item["price"] <= upper_bound
    ]
    if not clean_items:
        return None

    clean_prices = [item["price"] for item in clean_items]

    return {
        "category": items[0]["category"],
        "total": len(items),
        "clean_count": len(clean_items),
        "outliers_low": sum(price < lower_bound for price in prices),
        "outliers_high": sum(price > upper_bound for price in prices),
        "min": min(clean_prices),
        "median": statistics.median(clean_prices),
        "average": statistics.mean(clean_prices),
        "max": max(clean_prices),
        "q1": q1,
        "q3": q3,
        "lower_bound": lower_bound,
        "upper_bound": upper_bound,
        "clean_items": clean_items,
    }


def load_items(conn):
    """Загружает записи из базы."""
    rows = conn.execute(
        """
        SELECT category, title, price, seller, url
        FROM kworks
        WHERE price IS NOT NULL
        """
    ).fetchall()

    items = []
    for category, title, price_text, seller, url in rows:
        price = parse_price(price_text)
        if price is None or not category:
            continue
        items.append(
            {
                "category": category,
                "title": title or "(без названия)",
                "price": price,
                "seller": seller or "",
                "url": url or "",
            }
        )
    return items


def write_csv(path, headers, rows):
    """Сохраняет CSV-файл."""
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def build_report(items, total_rows):
    """Формирует текстовый отчёт."""
    grouped = {}
    for item in items:
        grouped.setdefault(item["category"], []).append(item)

    stats = []
    for category_items in grouped.values():
        result = get_category_stats(category_items)
        if result:
            stats.append(result)

    stats.sort(key=lambda row: row["average"], reverse=True)

    report_lines = [
        "АНАЛИЗ СТОИМОСТИ УСЛУГ НА KWORK",
        "=" * 72,
        f"Записей в базе: {total_rows}",
        f"Карточек с распознанной ценой: {len(items)}",
        "Выбросы определены по правилу 1.5 × IQR. Статистика без них.",
        "",
    ]

    if not stats:
        report_lines.append(
            "Пока недостаточно данных для сравнения: нужно не менее "
            "четырёх цен в категории."
        )
        return report_lines, [], []

    report_lines.append("СРАВНЕНИЕ КАТЕГОРИЙ")
    report_lines.append("=" * 72)
    for row in stats:
        report_lines.append(
            f"{row['category']}: предложений {row['total']}, "
            f"после фильтрации {row['clean_count']}; "
            f"медиана {row['median']:.0f} ₽, средняя {row['average']:.0f} ₽, "
            f"диапазон {row['min']}..{row['max']} ₽."
        )

    highest_median = max(stats, key=lambda row: row["median"])
    lowest_median = min(stats, key=lambda row: row["median"])
    report_lines.extend(
        [
            "",
            "КОРОТКО ПО РЕЗУЛЬТАТАМ",
            "Самая высокая медианная цена:",
            f"{highest_median['category']} ({highest_median['median']:.0f} ₽).",
            f"Самая низкая медианная цена: {lowest_median['category']} "
            f"({lowest_median['median']:.0f} ₽).",
        ]
    )

    summary_rows = [
        {
            "Категория": row["category"],
            "Всего с ценой": row["total"],
            "После фильтрации": row["clean_count"],
            "Нижние выбросы": row["outliers_low"],
            "Верхние выбросы": row["outliers_high"],
            "Минимум, ₽": row["min"],
            "Медиана, ₽": round(row["median"]),
            "Средняя, ₽": round(row["average"]),
            "Максимум, ₽": row["max"],
        }
        for row in stats
    ]

    top_rows = []
    for row in stats:
        clean_items = row["clean_items"]
        for label, ordered_items in (
            (
                "Дорогие",
                sorted(clean_items, key=lambda i: i["price"], reverse=True)[:5],
            ),
            ("Дешёвые", sorted(clean_items, key=lambda i: i["price"])[:5]),
        ):
            for item in ordered_items:
                top_rows.append(
                    {
                        "Категория": row["category"],
                        "Подборка": label,
                        "Цена, ₽": item["price"],
                        "Название": item["title"],
                        "Продавец": item["seller"],
                        "Ссылка": item["url"],
                    }
                )

    return report_lines, summary_rows, top_rows


def main():
    if not DB_PATH.exists():
        print(f"База данных не найдена: {DB_PATH}")
        print("Сначала запустите run_parser.cmd.")
        input("\nНажмите Enter, чтобы закрыть окно...")
        return

    OUTPUT_DIR.mkdir(exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        items = load_items(conn)
        total_rows = conn.execute("SELECT COUNT(*) FROM kworks").fetchone()[0]

    if not items:
        print("В базе пока нет записей с распознаваемыми ценами.")
        print("Сначала запустите парсер и проверьте, появились ли карточки.")
        input("\nНажмите Enter, чтобы закрыть окно...")
        return

    report_lines, summary_rows, top_rows = build_report(items, total_rows)

    report_path = OUTPUT_DIR / "kwork_report.txt"
    summary_path = OUTPUT_DIR / "kwork_summary.csv"
    top_path = OUTPUT_DIR / "kwork_top_offers.csv"

    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    write_csv(
        summary_path,
        list(summary_rows[0].keys())
        if summary_rows
        else [
            "Категория",
            "Всего с ценой",
            "После фильтрации",
            "Нижние выбросы",
            "Верхние выбросы",
            "Минимум, ₽",
            "Медиана, ₽",
            "Средняя, ₽",
            "Максимум, ₽",
        ],
        summary_rows,
    )
    write_csv(
        top_path,
        ["Категория", "Подборка", "Цена, ₽", "Название", "Продавец", "Ссылка"],
        top_rows,
    )

    print("\n".join(report_lines))
    print("\nФайлы сохранены в папку output:")
    print(f"  {report_path.name}")
    print(f"  {summary_path.name}")
    print(f"  {top_path.name}")


if __name__ == "__main__":
    main()
