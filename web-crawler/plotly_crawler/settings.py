# Scrapy settings for plotly_crawler project

BOT_NAME = "plotly_crawler"

SPIDER_MODULES = ["plotly_crawler.spiders"]
NEWSPIDER_MODULE = "plotly_crawler.spiders"

ROBOTSTXT_OBEY = True

# Be polite with docs website traffic.
CONCURRENT_REQUESTS_PER_DOMAIN = 1
DOWNLOAD_DELAY = 1
RANDOMIZE_DOWNLOAD_DELAY = True

RETRY_TIMES = 3
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1
AUTOTHROTTLE_MAX_DELAY = 8
TELNETCONSOLE_ENABLED = False

USER_AGENT = (
    "plotly-crawler/1.0 (+dataset generation for local ML experimentation)"
)

ITEM_PIPELINES = {
    "plotly_crawler.pipelines.PlotlyValidationPipeline": 100,
    "plotly_crawler.pipelines.PlotlyDedupPipeline": 200,
}

FEED_EXPORT_ENCODING = "utf-8"
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
