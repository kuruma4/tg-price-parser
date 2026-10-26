"""Тесты разбора HTML: без сети, на локальной разметке."""
import unittest

from parser import Preset, parse_html, parse_number

FIXTURE = """
<div class="catalog">
  <article class="product_pod">
    <h3><a href="/book-1.html" title="Book One">Book One</a></h3>
    <p class="price_color">&pound;51.77</p>
    <p class="instock availability">In stock</p>
    <p class="star-rating Three"></p>
  </article>
  <article class="product_pod">
    <h3><a href="/book-2.html" title="Book Two">Book Two</a></h3>
    <p class="price_color">&pound;13.99</p>
    <p class="instock availability">In stock</p>
    <p class="star-rating Five"></p>
  </article>
</div>
"""

PRESET = Preset(
    name="test",
    url="https://example.com",
    item="article.product_pod",
    fields={
        "name": {"selector": "h3 a", "attr": "title"},
        "price": {"selector": "p.price_color", "number": True},
        "rating": {"selector": "p.star-rating", "attr": "class", "regex": r"star-rating (\w+)"},
        "link": {"selector": "h3 a", "attr": "href"},
    },
)


class ParseTest(unittest.TestCase):
    def test_two_cards(self):
        rows = parse_html(FIXTURE, PRESET)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["name"], "Book One")
        self.assertEqual(rows[0]["price"], "51.77")
        self.assertEqual(rows[0]["rating"], "Three")
        self.assertEqual(rows[1]["link"], "/book-2.html")

    def test_missing_field_is_empty_string(self):
        preset = Preset(name="t", url="u", item="article", fields={"nope": {"selector": ".nope"}})
        self.assertEqual(parse_html(FIXTURE, preset), [])

    def test_parse_number_variants(self):
        self.assertEqual(parse_number("1 299,90 руб."), 1299.90)
        self.assertEqual(parse_number("1.299.90"), 1299.90)
        self.assertEqual(parse_number("$45"), 45.0)
        self.assertIsNone(parse_number("нет в наличии"))


if __name__ == "__main__":
    unittest.main()
