import scrapy


class PlotlyExampleItem(scrapy.Item):
    page_url = scrapy.Field()
    page_title = scrapy.Field()
    section_title = scrapy.Field()
    graph_type = scrapy.Field()
    description = scrapy.Field()
    code_blocks = scrapy.Field()
    code_count = scrapy.Field()
    libraries_detected = scrapy.Field()
    tags = scrapy.Field()
    source = scrapy.Field()
