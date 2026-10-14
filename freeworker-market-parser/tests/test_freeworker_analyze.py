"""Тесты для анализатора Freeworker."""

from freeworker_analyze import get_category_stats, parse_price


class TestParsePrice:
    def test_with_space_and_ruble(self):
        assert parse_price("5 000 ₽") == 5000

    def test_with_nbsp(self):
        assert parse_price("15\xa0000 ₽") == 15000

    def test_without_ruble(self):
        assert parse_price("1000") == 1000

    def test_none(self):
        assert parse_price(None) is None

    def test_empty(self):
        assert parse_price("") is None

    def test_garbage(self):
        assert parse_price("обсуждается индивидуально") is None


class TestGetCategoryStats:
    def test_returns_none_if_less_than_four(self):
        items = [
            {"category": "Тест", "price": p, "title": "T", "seller": "", "url": ""}
            for p in (1000, 2000, 3000)
        ]
        assert get_category_stats(items) is None

    def test_median_and_average(self):
        items = [
            {"category": "Тест", "price": p, "title": "T", "seller": "", "url": ""}
            for p in (1000, 2000, 3000, 4000)
        ]
        result = get_category_stats(items)
        assert result is not None
        assert result["median"] == 2500
        assert result["average"] == 2500
        assert result["min"] == 1000
        assert result["max"] == 4000

    def test_outliers_are_detected(self):
        items = [
            {
                "category": "Тест",
                "price": 1000 + i * 10,
                "title": f"T{i}",
                "seller": "",
                "url": "",
            }
            for i in range(20)
        ]
        items.append(
            {
                "category": "Тест",
                "price": 1_000_000,
                "title": "OUT",
                "seller": "",
                "url": "",
            }
        )
        result = get_category_stats(items)
        assert result is not None
        assert result["outliers_high"] == 1
        clean_prices = [item["price"] for item in result["clean_items"]]
        assert 1_000_000 not in clean_prices
