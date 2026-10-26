# tg-price-parser

Парсер каталогов: сайт → CSV или Excel. Один файл, без базы и без браузера —
работает там, где контент отдаётся в HTML.

Нужен, когда надо регулярно собирать цены, наличие, характеристики или
контакты в таблицу: мониторинг цен конкурентов, наполнение каталога,
сбор базы для аналитики.

## Что умеет

- обход пагинации с ограничением по числу страниц и товаров;
- несколько полей с карточки: текст, атрибут, регулярка, число;
- `1 299,90 ₽` → `1299.90` (пробелы тысяч, запятая, точки-разделители);
- удаление дублей между страницами;
- повторы при 429/5xx и таймаутах, пауза между запросами;
- выгрузка в `.csv` (UTF-8 BOM — Excel открывает без танцев) или `.xlsx`
  с закреплённой шапкой и автоподбором ширины.

## Установка

```bash
git clone https://github.com/kuruma4/tg-price-parser
cd tg-price-parser
pip install -r requirements.txt
```

## Запуск

```bash
# демо на открытом тестовом каталоге
python parser.py --preset presets/books.json --out books.csv --max-items 50

# в Excel
python parser.py --preset presets/books.json --out books.xlsx
```

Вывод:

```
страница 1: 20 карточек, всего 20
страница 2: 20 карточек, всего 40
Готово: 40 строк -> books.csv
```

Результат (`example_output.csv` в репозитории):

```csv
name,price,in_stock,rating,link
A Light in the Attic,51.77,In stock,Three,a-light-in-the-attic_1000/index.html
Tipping the Velvet,53.74,In stock,One,tipping-the-velvet_999/index.html
Soumission,50.1,In stock,One,soumission_998/index.html
```

## Как описать новый сайт

Всё в JSON — код менять не нужно:

```json
{
  "name": "магазин",
  "url": "https://site.ru/catalog/page-1.html",
  "item": "article.product",
  "next_page": "a.next",
  "max_pages": 20,
  "fields": {
    "name":   {"selector": "h3 a", "attr": "title"},
    "price":  {"selector": ".price", "number": true},
    "sku":    {"selector": ".sku", "regex": "Артикул: (\\w+)"},
    "link":   {"selector": "h3 a", "attr": "href"},
    "rating": {"selector": ".stars", "attr": "class", "regex": "stars-(\\d)"}
  }
}
```

| Поле | Значение |
|---|---|
| `selector` | CSS-селектор внутри карточки |
| `attr` | `text` (по умолчанию), `href`, `src`, `title`, `class`… |
| `regex` | вытащить группу 1 из полученного текста |
| `number` | привести к числу (`1 299,90` → `1299.90`) |

## Тесты

```bash
python -m unittest discover -s tests -v
```

Разбор HTML проверяется на локальной разметке: сеть не нужна, тесты идут
за 0.1 с.

## Ограничения

- Только HTML. Если данные приходят через XHR/JSON — берётся JSON-эндпоинт,
  это другой пресет.
- Не обходит Cloudflare/капчу: для таких сайтов нужен браузер (Playwright),
  обсуждается отдельно.
- Запуск по расписанию (cron / Планировщик Windows) — настраивается под задачу.

## Заказ

Нужен парсер под свой сайт? Telegram: [@kuruma44](https://t.me/kuruma44)
