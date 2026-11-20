"""Tests for kspu.edu, Google News RSS, and Telegram @ksuniver parsers."""

from ksu_news_monitor.sources.google_news import parse_google_news_rss
from ksu_news_monitor.sources.kspu import parse_kspu_html, parse_kspu_rss
from ksu_news_monitor.sources.telegram_channel import parse_telegram_channel_html


def test_parse_kspu_rss():
    rss = """<?xml version="1.0" encoding="utf-8"?>
    <rss version="2.0">
      <channel>
        <item>
          <title>У ХДУ продовжують розвивати спільноту амбасадорів</title>
          <link>https://kspu.edu/PublisherReader?newsId=25721</link>
          <guid>https://kspu.edu/PublisherReader?newsId=25721</guid>
          <pubDate>Thu, 19 Nov 2026 17:18:07 GMT</pubDate>
          <description>&lt;p&gt;19 листопада у ХДУ відбувся тренінг.&lt;/p&gt;</description>
        </item>
      </channel>
    </rss>"""
    items = parse_kspu_rss(rss)
    assert len(items) == 1
    assert items[0].item_id == "kspu:25721"
    assert items[0].source == "kspu"
    assert items[0].summary == "19 листопада у ХДУ відбувся тренінг."


def test_parse_kspu_html_fallback():
    html_doc = """
    <article class="news-item">
      <div class="news-item__body">
        <h3 class="news-item__title">
          <a href="/PublisherReader?newsId=25717">Представниця ХДУ увійшла до складу журі</a>
        </h3>
        <div class="news-item__description"><p>Конкурс у Празі.</p></div>
        <div class="news-item__meta"><time datetime="2026-11-19">19 листопада 2026</time></div>
      </div>
    </article>"""
    items = parse_kspu_html(html_doc)
    assert len(items) == 1
    assert items[0].item_id == "kspu:25717"
    assert items[0].url == "https://kspu.edu/PublisherReader?newsId=25717"


def test_parse_google_news_rss_filters_kspu_mirror_and_false_positives():
    rss = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <item>
          <title>Херсонський державний університет оголошує набір - Український південь</title>
          <link>https://news.google.com/rss/articles/111</link>
          <guid isPermaLink="false">guid-111</guid>
          <pubDate>Wed, 18 Nov 2026 21:13:00 GMT</pubDate>
          <source url="https://pivdenukraine.com.ua">Український південь</source>
        </item>
        <item>
          <title>Новина на сайті ХДУ - kspu.edu</title>
          <link>https://news.google.com/rss/articles/222</link>
          <guid isPermaLink="false">guid-222</guid>
          <pubDate>Wed, 18 Nov 2026 20:00:00 GMT</pubDate>
          <source url="https://kspu.edu">kspu.edu</source>
        </item>
        <item>
          <title>Kherson State Agrarian and Economic University Enrollment - most.ks.ua</title>
          <link>https://news.google.com/rss/articles/333</link>
          <guid isPermaLink="false">guid-333</guid>
          <pubDate>Wed, 18 Nov 2026 19:00:00 GMT</pubDate>
          <source url="https://most.ks.ua">most.ks.ua</source>
        </item>
      </channel>
    </rss>"""
    items = parse_google_news_rss(rss)
    assert len(items) == 1
    assert items[0].title == "Херсонський державний університет оголошує набір"
    assert items[0].publisher == "Український південь"


def test_parse_telegram_channel_html():
    html_doc = """
    <div class="tgme_widget_message" data-post="ksuniver/1786">
      <div class="tgme_widget_message_text">&#8203;&#8203;Ректор ХДУ презентував можливості AI<br/>30 жовтня відбулася лекція.</div>
      <a class="tgme_widget_message_date" href="https://t.me/ksuniver/1786">
        <time datetime="2026-11-19T07:51:24+00:00">07:51</time>
      </a>
    </div>
    <div class="tgme_widget_message" data-post="ksuniver/1787">
      <a class="tgme_widget_message_date" href="https://t.me/ksuniver/1787">
        <time datetime="2026-11-19T08:00:00+00:00">08:00</time>
      </a>
    </div>"""
    items = parse_telegram_channel_html(html_doc, channel="ksuniver")
    assert len(items) == 2
    assert items[0].item_id == "tg:ksuniver/1786"
    assert items[0].title == "Ректор ХДУ презентував можливості AI"
    assert items[0].summary == "30 жовтня відбулася лекція."
    assert items[1].item_id == "tg:ksuniver/1787"
    assert "медіа" in items[1].title.lower()
