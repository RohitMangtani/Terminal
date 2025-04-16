import feedparser
from datetime import datetime
from typing import List, Dict, Any
import pytz
import time
import re

# Define financial news RSS feed URLs
FINANCIAL_FEEDS = [
    {"url": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC&region=US&lang=en-US", "source": "Yahoo Finance"},
    {"url": "https://www.cnbc.com/id/100003114/device/rss/rss.html", "source": "CNBC Markets"},
    {"url": "http://feeds.reuters.com/reuters/businessNews", "source": "Reuters Business"},
    {"url": "https://www.ft.com/world/rss", "source": "Financial Times"},
    # Bloomberg added via a common RSS aggregator that provides their content
    {"url": "https://feedly.com/f/alert/rss/0c53d59a-2e5e-4daa-8a35-f3c77cf1d1f3", "source": "Bloomberg (via Feedly)"},
]

def standardize_timestamp(timestamp_str: str) -> str:
    """Convert various timestamp formats to UTC ISO format."""
    if not timestamp_str:
        return datetime.now(pytz.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Common RSS date formats to try
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",      # RFC 822 format with timezone
        "%a, %d %b %Y %H:%M:%S %Z",      # RFC 822 format with timezone name
        "%a, %d %b %Y %H:%M:%S",         # RFC 822 format without timezone
        "%Y-%m-%dT%H:%M:%S%z",           # ISO 8601 format
        "%Y-%m-%dT%H:%M:%SZ",            # ISO 8601 UTC format
        "%Y-%m-%d %H:%M:%S",             # Simple datetime format
        "%a %b %d %H:%M:%S %Y",          # Unix ctime format
        "%d %b %Y %H:%M:%S",             # Another common format
    ]
    
    dt = None
    
    # Try each format
    for fmt in formats:
        try:
            dt = datetime.strptime(timestamp_str, fmt)
            break
        except ValueError:
            continue
    
    # If none of the formats matched, try to parse with dateutil as fallback
    if dt is None:
        try:
            # Try to handle the case where there's a GMT offset like GMT-5:00
            gmt_match = re.search(r'GMT([+-]\d+):(\d+)', timestamp_str)
            if gmt_match:
                hours, minutes = int(gmt_match.group(1)), int(gmt_match.group(2))
                # Remove the GMT offset part for parsing
                clean_str = re.sub(r'GMT[+-]\d+:\d+', '', timestamp_str).strip()
                
                for fmt in formats:
                    try:
                        dt = datetime.strptime(clean_str, fmt)
                        # Apply the GMT offset
                        offset = hours * 3600 + (minutes * 60 if hours >= 0 else -minutes * 60)
                        dt = dt.replace(tzinfo=pytz.FixedOffset(offset // 60))
                        break
                    except ValueError:
                        continue
            
            # If still not parsed, just use current time
            if dt is None:
                dt = datetime.fromtimestamp(time.mktime(time.strptime(timestamp_str)))
        except Exception:
            # If all parsing attempts fail, return current time
            dt = datetime.now(pytz.UTC)
    
    # Ensure the datetime is timezone-aware and convert to UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=pytz.UTC)
    else:
        dt = dt.astimezone(pytz.UTC)
    
    # Return in ISO format
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def fetch_rss_headlines() -> List[Dict[str, Any]]:
    """
    Fetch headlines from financial RSS feeds.
    
    Returns:
        List of dictionaries containing headline information with keys:
        - title: The headline title
        - link: URL to the full article
        - published: Publication timestamp in UTC ISO format
        - source: Name of the source (Yahoo Finance, CNBC, Reuters)
    """
    headlines = []
    
    for feed_info in FINANCIAL_FEEDS:
        try:
            # Parse the feed
            feed = feedparser.parse(feed_info["url"])
            
            # Process each entry in the feed
            for entry in feed.entries:
                # Try to get published date from different possible fields
                published_date = entry.get("published", "")
                if not published_date:
                    published_date = entry.get("pubDate", "")
                if not published_date:
                    published_date = entry.get("updated", "")
                
                # Extract and clean the relevant data
                headline = {
                    "title": entry.get("title", "").strip(),
                    "link": entry.get("link", "").strip(),
                    "published": standardize_timestamp(published_date),
                    "source": feed_info["source"]
                }
                
                # Try to get summary/description if available
                if hasattr(entry, "summary"):
                    headline["summary"] = entry.summary
                elif hasattr(entry, "description"):
                    headline["summary"] = entry.description
                
                # Only add non-empty headlines
                if headline["title"] and headline["link"]:
                    headlines.append(headline)
                    
        except Exception as e:
            print(f"Error fetching feed {feed_info['url']}: {str(e)}")
    
    return headlines

if __name__ == "__main__":
    # Test the functionality
    headlines = fetch_rss_headlines()
    
    # Print the first few headlines
    for headline in headlines[:5]:
        print(f"Title: {headline['title']}")
        print(f"Source: {headline['source']}")
        print(f"Published: {headline['published']}")
        print(f"Link: {headline['link']}")
        if "summary" in headline:
            print(f"Summary: {headline['summary'][:100]}...")
        print("-" * 50) 