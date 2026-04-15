import re
from urllib.parse import urljoin, urlparse

import scrapy
from itemloaders import ItemLoader
from itemloaders.processors import Identity, TakeFirst

from plotly_crawler.items import PlotlyExampleItem


def clean_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def detect_libs(code_blocks):
    joined = "\n".join(code_blocks).lower()
    libs = []
    if "plotly.express" in joined or "import plotly.express as px" in joined:
        libs.append("plotly.express")
    if "plotly.graph_objects" in joined or "import plotly.graph_objects as go" in joined:
        libs.append("plotly.graph_objects")
    if "make_subplots" in joined:
        libs.append("plotly.subplots")
    return libs


class PlotlyPythonSpider(scrapy.Spider):
    name = "plotly_python"
    allowed_domains = ["plotly.com"]
    start_urls = ["https://plotly.com/python/"]

    custom_settings = {
        "LOG_LEVEL": "INFO",
    }

    def parse(self, response):
        page_title = clean_text(response.css("h1::text").get() or response.css("title::text").get())
        description = clean_text(
            response.css('meta[name="description"]::attr(content)').get()
            or " ".join(response.css("main p::text").getall()[:2])
        )
        graph_type = self.infer_graph_type(response.url, page_title)
        tags = self.extract_tags(response.url, page_title)

        for block in self.extract_python_blocks_with_sections(response):
            loader = ItemLoader(item=PlotlyExampleItem(), response=response)
            loader.default_output_processor = TakeFirst()
            loader.code_blocks_out = Identity()
            loader.libraries_detected_out = Identity()
            loader.tags_out = Identity()

            loader.add_value("page_url", response.url)
            loader.add_value("page_title", page_title)
            loader.add_value("section_title", block["section_title"])
            loader.add_value("graph_type", graph_type)
            loader.add_value("description", description)
            loader.add_value("code_blocks", [block["code"]])
            loader.add_value("code_count", 1)
            loader.add_value("libraries_detected", detect_libs([block["code"]]))
            loader.add_value("tags", tags)
            loader.add_value("source", "https://plotly.com/python/")
            yield loader.load_item()

        for href in response.css('a[href*="/python/"]::attr(href)').getall():
            absolute = urljoin(response.url, href)
            if self.should_follow(absolute):
                yield response.follow(absolute, callback=self.parse)

    def should_follow(self, url):
        parsed = urlparse(url)
        if parsed.netloc and parsed.netloc != "plotly.com":
            return False
        if "/python/" not in parsed.path:
            return False
        blocked_parts = ("/javascript/", "/r/", "/julia/", "/matlab/", "/api-reference/")
        return not any(part in parsed.path for part in blocked_parts)

    def extract_python_blocks_with_sections(self, response):
        blocks = []
        seen = set()
        candidates = response.xpath("//div[contains(@class,'highlight')]/pre")

        for pre in candidates:
            text_parts = pre.xpath(".//text()").getall()
            raw_code = "".join(text_parts)
            cleaned = raw_code.strip()
            if not cleaned or not self.looks_like_python_plotly(cleaned):
                continue

            section_title = pre.xpath(
                "normalize-space(preceding::*[self::h2 or self::h3 or self::h4][1])"
            ).get() or response.css("h1::text").get() or "untitled-section"
            section_title = clean_text(section_title)

            key = (section_title, cleaned)
            if key in seen:
                continue
            seen.add(key)
            blocks.append({"section_title": section_title, "code": cleaned})
        return blocks

    def looks_like_python_plotly(self, block):
        lower = block.lower()
        python_signals = ("import ", "def ", "fig.", "px.", "go.", "plotly")
        return any(signal in lower for signal in python_signals)

    def infer_graph_type(self, url, title):
        path = urlparse(url).path.lower().strip("/")
        slug = path.split("/")[-1] if path else ""
        known_types = [
            "line-charts",
            "scatter-plots",
            "bar-charts",
            "histograms",
            "box-plots",
            "violin-plots",
            "heatmaps",
            "pie-charts",
            "sunburst-charts",
            "treemaps",
            "area-charts",
            "3d-scatter-plots",
            "choropleth-maps",
            "mapbox-layers",
            "candlestick-charts",
            "sankey-diagram",
            "funnel-charts",
            "waterfall-charts",
            "parallel-coordinates-plot",
        ]
        if slug in known_types:
            return slug
        if title:
            return title.lower().replace(" ", "-")
        return "unknown"

    def extract_tags(self, url, title):
        tags = []
        path = urlparse(url).path.lower()
        for token in ["map", "3d", "animation", "subplot", "facet", "express", "graph_objects"]:
            if token in path or token in (title or "").lower():
                tags.append(token)
        return tags
