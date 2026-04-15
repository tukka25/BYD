# Plotly Python Scraper (Scrapy)

This crawler extracts Plotly Python graph examples from `https://plotly.com/python/`.

## Spider
- Name: `plotly_python`
- Scope: `plotly.com/python/*`
- Output fields:
  - `page_url`
  - `page_title`
  - `section_title`
  - `graph_type`
  - `description`
  - `code_blocks` (list, currently one block per item)
  - `code_count`
  - `libraries_detected`
  - `tags`
  - `source`

## Run

```bash
cd web-crawler
source venv/bin/activate

# Small test crawl
scrapy crawl plotly_python -s CLOSESPIDER_PAGECOUNT=10 -O plotly_examples_sample.jsonl

# Full crawl dataset
scrapy crawl plotly_python -O plotly_examples.jsonl
```

## Notes
- `ROBOTSTXT_OBEY=True` is enabled.
- Crawl speed is throttled with `DOWNLOAD_DELAY` and `AUTOTHROTTLE`.
- Pipelines validate required fields and de-duplicate by `(page_url, section_title)`.
