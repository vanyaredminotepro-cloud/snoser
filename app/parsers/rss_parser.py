import asyncio
import logging
from dataclasses import dataclass

import feedparser

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RssItem:
    feed_key: str
    title: str
    summary: str
    link: str


class RSSParser:
    async def fetch(self, feed_key: str, url: str) -> list[RssItem]:
        parsed = await asyncio.to_thread(feedparser.parse, url)
        if getattr(parsed, "bozo", False):
            logger.warning("RSS parse warning for %s: %s", feed_key, getattr(parsed, "bozo_exception", "unknown"))

        items: list[RssItem] = []
        for entry in parsed.entries[:10]:
            title = str(getattr(entry, "title", "")).strip()
            summary = str(getattr(entry, "summary", "")).strip()
            link = str(getattr(entry, "link", "")).strip()
            if title:
                items.append(RssItem(feed_key=feed_key, title=title, summary=summary, link=link))
        return items
