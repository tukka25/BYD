from scrapy.exceptions import DropItem


class PlotlyValidationPipeline:
    def process_item(self, item):
        if not item.get("page_url"):
            raise DropItem("Missing page_url")
        if not item.get("code_blocks"):
            raise DropItem("Missing code blocks")
        return item


class PlotlyDedupPipeline:
    def __init__(self):
        self._seen = set()

    def process_item(self, item):
        key = (item.get("page_url"), item.get("section_title"))
        if key in self._seen:
            raise DropItem(f"Duplicate item: {key}")
        self._seen.add(key)
        return item
