#!/usr/bin/env python
"""
EVENT TAGGER MODULE
==================

What This Module Does:
--------------------
This module analyzes financial headlines and market context to generate
event-level tags that provide additional context for trade decisions.

How to Use:
----------
1. Generate tags for an event:
   from event_tagger import generate_event_tags
   tags = generate_event_tags(headline, macro_snapshot, event_date, ticker)

What This Helps You See:
-----------------------
- Whether an event represents a positive surprise
- If the event occurs during key market periods (Fed meetings, CPI releases, earnings)
- If similar events have occurred recently (repeat events)
- Provides structured context that can be used for pattern matching and backtesting
"""

import re
import json
import os
import datetime
from typing import Dict, Any, List, Optional, Set, Tuple
from datetime import datetime, timedelta

# Constants for keyword matching
POSITIVE_SURPRISE_KEYWORDS = {
    'beat', 'beats', 'exceeds', 'exceeded', 'higher than expected', 'better than expected',
    'surprise', 'surprised', 'surprising', 'outperform', 'outperformed', 'outperforms',
    'above expectations', 'positive surprise', 'strong', 'stronger', 'strongest', 'record',
    'surge', 'surged', 'surges', 'jump', 'jumped', 'jumps', 'rally', 'rallied', 'rallies'
}

NEGATIVE_SURPRISE_KEYWORDS = {
    'miss', 'misses', 'missed', 'below', 'lower than expected', 'worse than expected', 
    'disappoint', 'disappoints', 'disappointed', 'disappointing', 'underperform', 'underperformed',
    'underperforms', 'below expectations', 'negative surprise', 'weak', 'weaker', 'weakest',
    'drop', 'dropped', 'drops', 'fall', 'fell', 'falls', 'plunge', 'plunged', 'plunges',
    'slump', 'slumped', 'slumps', 'tank', 'tanked', 'tanks'
}

FED_KEYWORDS = {
    'fed', 'federal reserve', 'powell', 'fomc', 'rate decision', 'interest rate', 'monetary policy',
    'central bank', 'rate hike', 'rate cut', 'dovish', 'hawkish', 'taper', 'quantitative'
}

CPI_KEYWORDS = {
    'cpi', 'inflation', 'consumer price', 'pce', 'price index', 'inflationary',
    'deflation', 'deflationary', 'core inflation', 'prices rose', 'prices increased'
}

EARNINGS_KEYWORDS = {
    'earnings', 'eps', 'revenue', 'profit', 'loss', 'quarterly', 'q1', 'q2', 'q3', 'q4',
    'quarter', 'fiscal', 'guidance', 'outlook', 'forecast', 'results', 'performance'
}

# Calendar data (approximate, would need regular updates in production)
FED_MEETING_MONTHS = {1, 3, 5, 6, 8, 9, 11, 12}  # FOMC typically meets 8 times a year
CPI_RELEASE_DAY_RANGE = range(10, 16)  # CPI typically released between 10th-15th of month
EARNINGS_SEASONS = [
    (1, 15, 2, 15),   # Jan 15 - Feb 15 (Q4 earnings)
    (4, 15, 5, 15),   # Apr 15 - May 15 (Q1 earnings)
    (7, 15, 8, 15),   # Jul 15 - Aug 15 (Q2 earnings)
    (10, 15, 11, 15)  # Oct 15 - Nov 15 (Q3 earnings)
]

# Static list of FOMC meeting dates (2023-2024)
# In a production system, these would be loaded from an external source
# and updated regularly
FOMC_MEETING_DATES = [
    # 2023 meetings
    datetime(2023, 1, 31), datetime(2023, 2, 1),
    datetime(2023, 3, 21), datetime(2023, 3, 22),
    datetime(2023, 5, 2), datetime(2023, 5, 3),
    datetime(2023, 6, 13), datetime(2023, 6, 14),
    datetime(2023, 7, 25), datetime(2023, 7, 26),
    datetime(2023, 9, 19), datetime(2023, 9, 20),
    datetime(2023, 10, 31), datetime(2023, 11, 1),
    datetime(2023, 12, 12), datetime(2023, 12, 13),
    # 2024 meetings
    datetime(2024, 1, 30), datetime(2024, 1, 31),
    datetime(2024, 3, 19), datetime(2024, 3, 20),
    datetime(2024, 4, 30), datetime(2024, 5, 1),
    datetime(2024, 6, 11), datetime(2024, 6, 12),
    datetime(2024, 7, 30), datetime(2024, 7, 31),
    datetime(2024, 9, 17), datetime(2024, 9, 18),
    datetime(2024, 11, 6), datetime(2024, 11, 7),
    datetime(2024, 12, 17), datetime(2024, 12, 18)
]

# Cache for recent events to detect repeats (in-memory cache that would be lost on restart)
_recent_events_cache: List[Tuple[str, str, datetime]] = []
_MAX_CACHE_SIZE = 1000

# Path to trade history file for repeat event detection
DEFAULT_TRADE_HISTORY_FILE = "trade_history.json"

def generate_event_tags(headline: str, 
                        macro_snapshot: Dict[str, float],
                        event_date: datetime,
                        ticker: str,
                        trade_history_file: str = DEFAULT_TRADE_HISTORY_FILE) -> Dict[str, bool]:
    """
    Generate context tags for a financial event based on headline, market data, and timing.
    
    Args:
        headline: The headline text describing the event
        macro_snapshot: Dictionary of macroeconomic indicators
        event_date: Date when the event occurred
        ticker: The affected stock/ETF ticker symbol
        trade_history_file: Path to the trade history JSON file (default: "trade_history.json")
        
    Returns:
        Dictionary with boolean tags:
        {
            "surprise_positive": True if event represents positive surprise,
            "is_fed_week": True if event occurs during Fed meeting week,
            "is_cpi_week": True if event occurs during CPI release week,
            "is_earnings_season": True if event occurs during earnings season,
            "is_repeat_event": True if similar event occurred recently
        }
    """
    # Initialize tags with default values
    tags = {
        "surprise_positive": False,
        "is_fed_week": False,
        "is_cpi_week": False,
        "is_earnings_season": False,
        "is_repeat_event": False
    }
    
    # Normalize headline text for matching
    norm_headline = headline.lower()
    
    # Rule 1: Check for positive surprise
    # Original logic: Check for positive sentiment keywords
    if any(keyword in norm_headline for keyword in POSITIVE_SURPRISE_KEYWORDS):
        # If there are negative keywords too, determine which sentiment is stronger
        if any(keyword in norm_headline for keyword in NEGATIVE_SURPRISE_KEYWORDS):
            pos_count = sum(1 for keyword in POSITIVE_SURPRISE_KEYWORDS if keyword in norm_headline)
            neg_count = sum(1 for keyword in NEGATIVE_SURPRISE_KEYWORDS if keyword in norm_headline)
            tags["surprise_positive"] = pos_count > neg_count
        else:
            tags["surprise_positive"] = True
    
    # Enhanced Rule 1: CPI surprise detection
    # If headline mentions CPI and actual CPI is higher than expected CPI
    if 'cpi' in norm_headline and macro_snapshot and 'CPI_YoY' in macro_snapshot and 'CPI_Expected' in macro_snapshot:
        # Higher inflation than expected is typically negative for markets
        if macro_snapshot['CPI_YoY'] > macro_snapshot['CPI_Expected']:
            tags["surprise_positive"] = False
        elif macro_snapshot['CPI_YoY'] < macro_snapshot['CPI_Expected']:
            # Lower than expected inflation is typically positive
            tags["surprise_positive"] = True
    
    # Rule 2: Check if it's Fed meeting week
    # Original logic: Check for Fed meeting months and days
    month = event_date.month
    day = event_date.day
    
    # Enhanced Rule 2: Check if the event date is within 3 business days of any FOMC meeting date
    # Business days are approximated (weekends not considered) for simplicity
    for fomc_date in FOMC_MEETING_DATES:
        # Check if the event is within +/- 3 days of a FOMC meeting
        date_diff = abs((event_date.date() - fomc_date.date()).days)
        if date_diff <= 3:
            tags["is_fed_week"] = True
            break
    
    # Rule 3: Check if it's CPI release week
    # Enhanced Rule 3: Direct check for CPI mention and data
    if 'cpi' in norm_headline and macro_snapshot and 'CPI_YoY' in macro_snapshot and macro_snapshot['CPI_YoY'] is not None:
        tags["is_cpi_week"] = True
    
    # Rule 4: Check if it's earnings season
    # Enhanced Rule 4: Check for mid-month of earnings quarter months
    event_month = event_date.month
    event_day = event_date.day
    
    # Earnings seasons occur in mid-Jan, mid-Apr, mid-Jul, and mid-Oct
    if ((event_month == 1 or event_month == 4 or event_month == 7 or event_month == 10) and
        (event_day >= 10 and event_day <= 25)):
        tags["is_earnings_season"] = True
    
    # Rule 5: Check if it's a repeat event
    # Enhanced Rule 5: Check if headline or ticker appears in trade history
    # Load trade history if the file exists
    if os.path.exists(trade_history_file):
        try:
            with open(trade_history_file, 'r') as f:
                trade_history = json.load(f)
            
            # Filter for trades within the last 30 days
            thirty_days_ago = event_date - timedelta(days=30)
            
            for trade in trade_history:
                # Check if trade has timestamp and headline
                if 'timestamp' in trade and 'headline' in trade:
                    try:
                        # Parse the timestamp
                        trade_date = datetime.fromisoformat(trade['timestamp'])
                        
                        # Check if trade is within the last 30 days
                        if trade_date >= thirty_days_ago:
                            trade_headline = trade.get('headline', '').lower()
                            trade_ticker = trade.get('ticker', '').lower()
                            
                            # Check for similar headline or same ticker
                            headline_similarity = _calculate_text_similarity(norm_headline, trade_headline)
                            
                            if headline_similarity > 0.7 or ticker.lower() == trade_ticker:
                                tags["is_repeat_event"] = True
                                break
                    except (ValueError, TypeError):
                        # Skip trades with invalid timestamps
                        continue
        except Exception as e:
            print(f"Warning: Error reading trade history file: {str(e)}")
    
    # Use in-memory cache as fallback if trade history file doesn't exist or can't be read
    if not tags["is_repeat_event"]:
        normalized_tokens = _normalize_headline_for_comparison(norm_headline)
        event_key = (ticker.lower(), ''.join(normalized_tokens))
        
        # Create a mini-hash of the event for faster comparison
        event_hash = hash(event_key)
        
        # Check if this event is similar to recent events in memory cache
        for cached_ticker, cached_hash, cached_date in _recent_events_cache:
            # Only consider events within the last 30 days
            if (event_date - cached_date).days <= 30:
                if cached_ticker == ticker.lower() and _calculate_similarity(event_hash, cached_hash) > 0.8:
                    tags["is_repeat_event"] = True
                    break
    
    # Add this event to the in-memory cache for future comparisons
    _add_to_event_cache(ticker.lower(), hash((ticker.lower(), ''.join(_normalize_headline_for_comparison(norm_headline)))), event_date)
    
    return tags

def _month_day_to_ordinal(month: int, day: int, year: int) -> int:
    """
    Convert month and day to an ordinal date value for comparison.
    
    Args:
        month: Month (1-12)
        day: Day of month
        year: Year
        
    Returns:
        Ordinal date value
    """
    try:
        return datetime.date(year, month, day).toordinal()
    except ValueError:
        # Handle invalid dates (like Feb 30) by returning last day of month
        if month == 2:
            # Check for leap year
            if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
                return datetime.date(year, 2, 29).toordinal()
            else:
                return datetime.date(year, 2, 28).toordinal()
        elif month in [4, 6, 9, 11]:  # 30-day months
            return datetime.date(year, month, 30).toordinal()
        else:  # 31-day months
            return datetime.date(year, month, 31).toordinal()

def _normalize_headline_for_comparison(headline: str) -> List[str]:
    """
    Normalize a headline for comparison to detect repeat events.
    Removes numbers, dates, and common filler words.
    
    Args:
        headline: Headline text
        
    Returns:
        List of normalized content words
    """
    # Remove numbers, special chars, and convert to lowercase
    text = re.sub(r'[0-9]+', '', headline)
    text = re.sub(r'[^\w\s]', '', text)
    
    # Remove common filler words 
    stopwords = {'a', 'an', 'the', 'and', 'or', 'but', 'if', 'as', 'at', 'by', 'for', 'in', 'to', 'with'}
    tokens = text.lower().split()
    content_tokens = [word for word in tokens if word not in stopwords and len(word) > 2]
    
    return content_tokens

def _calculate_similarity(hash1: int, hash2: int) -> float:
    """
    Calculate similarity between two hash values.
    This is a simplified comparison - a real implementation would use proper similarity measure.
    
    Args:
        hash1: First hash value
        hash2: Second hash value
        
    Returns:
        Similarity score (0.0 to 1.0)
    """
    # This is a very simple hash comparison - not robust
    # A real implementation would use Jaccard similarity or other text similarity measures
    # This is just for demonstration purposes
    if hash1 == hash2:
        return 1.0
    
    # XOR the hashes and count bits that are different
    xor_result = hash1 ^ hash2
    # Count bits set to 1 (different bits)
    bit_diff = bin(xor_result).count('1')
    
    # Normalize to a similarity score
    # More different bits = lower similarity
    return max(0.0, 1.0 - (bit_diff / 64.0))  # Assuming 64-bit hashes

def _calculate_text_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity between two text strings using Jaccard similarity of words.
    
    Args:
        text1: First text
        text2: Second text
        
    Returns:
        Similarity score (0.0 to 1.0)
    """
    # Normalize and tokenize both texts
    tokens1 = set(_normalize_headline_for_comparison(text1))
    tokens2 = set(_normalize_headline_for_comparison(text2))
    
    # Calculate Jaccard similarity: intersection over union
    if not tokens1 or not tokens2:
        return 0.0
        
    intersection = len(tokens1.intersection(tokens2))
    union = len(tokens1.union(tokens2))
    
    return intersection / union if union > 0 else 0.0

def _add_to_event_cache(ticker: str, event_hash: int, event_date: datetime) -> None:
    """
    Add an event to the cache for future repeat detection.
    Maintains a fixed-size cache with FIFO eviction policy.
    
    Args:
        ticker: Stock ticker
        event_hash: Hash of normalized event
        event_date: Date of event
    """
    global _recent_events_cache
    
    # Add to cache
    _recent_events_cache.append((ticker, event_hash, event_date))
    
    # If cache exceeds max size, remove oldest entries
    if len(_recent_events_cache) > _MAX_CACHE_SIZE:
        _recent_events_cache = _recent_events_cache[-_MAX_CACHE_SIZE:]

def is_keyword_in_text(text: str, keywords: Set[str]) -> bool:
    """
    Check if any keyword appears in the text.
    
    Args:
        text: Text to search in
        keywords: Set of keywords to search for
        
    Returns:
        True if any keyword is found in the text
    """
    normalized_text = text.lower()
    return any(keyword in normalized_text for keyword in keywords)

# Demo usage
if __name__ == "__main__":
    import sys
    
    # Example headline
    test_headline = "Apple beats earnings expectations, stock jumps 5% in after-hours trading"
    
    # Example data
    test_date = datetime.now()
    test_ticker = "AAPL"
    test_macro = {
        "CPI_YoY": 3.2,
        "CPI_Expected": 3.3,  # Expected inflation was higher than actual (positive)
        "FedFundsRate": 5.25,
        "VIX": 18.5
    }
    
    # Generate tags
    if len(sys.argv) > 1:
        test_headline = sys.argv[1]  # Use command line argument if provided
        
    tags = generate_event_tags(test_headline, test_macro, test_date, test_ticker)
    
    # Print results
    print(f"Headline: {test_headline}")
    print(f"Date: {test_date.strftime('%Y-%m-%d')}")
    print(f"Ticker: {test_ticker}")
    print("\nMacro Data:")
    for key, value in test_macro.items():
        print(f"  {key}: {value}")
    
    print("\nGenerated Tags:")
    for tag, value in tags.items():
        print(f"  {tag}: {value}")
    
    # Test with CPI headline
    cpi_headline = "CPI rises 3.2%, slightly below expectations"
    cpi_tags = generate_event_tags(cpi_headline, test_macro, test_date, "SPY")
    
    print("\nTest with CPI Headline:")
    print(f"Headline: {cpi_headline}")
    print("Generated Tags:")
    for tag, value in cpi_tags.items():
        print(f"  {tag}: {value}") 