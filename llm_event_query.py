#!/usr/bin/env python
"""
LLM Event Query
==============

This script provides a tool to query the LLM about market events
and get trade recommendations based on the analysis of those events.

Features:
- Accepts natural language queries about market events
- Uses OpenAI to parse and understand the query
- Pulls relevant macroeconomic data
- Generates trade ideas based on the event analysis
- Returns detailed rationale for the trade recommendation

Usage:
   python llm_event_query.py "What happened when Bitcoin ETF was approved?"
"""

import os
import json
import sys
import openai
import re
import time
import random
import datetime
from datetime import datetime, timedelta
from dotenv import load_dotenv
from macro_data_collector import get_macro_snapshot, get_fred_data, FRED_METRICS, FALLBACK_VALUES
from options_data_collector import get_options_snapshot
from event_tagger import generate_event_tags
from llm_event_classifier import classify_macro_event
from trade_picker import generate_trade_idea
from event_analyzer import standardize_ticker, fetch_market_data, calculate_price_changes
from historical_matcher import find_similar_historical_events, DEFAULT_MARKET_TICKER
import pandas as pd
import requests
from fredapi import Fred
import logging
import argparse
import uuid

# Import custom modules
from sentiment_analyzer import add_sentiment_comparison_to_analysis, compare_sentiment
import analysis_persistence as ap
from rss_ingestor import fetch_rss_headlines
import html

# Load environment variables
load_dotenv()

# Get API keys from environment
# Read API key directly from .env file to ensure we get the current value
try:
    with open('.env', 'r') as f:
        env_contents = f.read()
        for line in env_contents.splitlines():
            if line.startswith('OPENAI_API_KEY='):
                OPENAI_API_KEY = line.split('=', 1)[1]
                print(f"✅ OpenAI API key loaded directly from .env file: {OPENAI_API_KEY[:4]}...{OPENAI_API_KEY[-4:]}")
                break
        else:
            OPENAI_API_KEY = None
            print("❌ ERROR: OPENAI_API_KEY not found in .env file")
except Exception as e:
    print(f"❌ ERROR reading .env file: {str(e)}")
    OPENAI_API_KEY = None

# Fallback to environment variable if direct read failed
if not OPENAI_API_KEY:
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    if OPENAI_API_KEY:
        print(f"✅ OpenAI API key loaded from environment variable: {OPENAI_API_KEY[:4]}...{OPENAI_API_KEY[-4:]}")
    else:
        print("❌ ERROR: OpenAI API key not found in environment")
        print("Please add your OpenAI API key to the .env file with the variable name OPENAI_API_KEY")

# Set the API key for the openai module
openai.api_key = OPENAI_API_KEY

# Define default model from environment or use a fallback
DEFAULT_MODEL = os.getenv('OPENAI_MODEL', "gpt-3.5-turbo")

# Initialize FRED API if available
FRED_API_KEY = os.getenv('FRED_API_KEY')
fred = Fred(api_key=FRED_API_KEY) if FRED_API_KEY else None

# API retry configuration
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2

# Error message templates
ERROR_MESSAGES = {
    "openai_connection": "Connection to OpenAI API failed. Retrying... (attempt {}/{})",
    "openai_auth": "OpenAI authentication failed. Please check your API key.",
    "openai_rate_limit": "OpenAI rate limit exceeded. Waiting for {} seconds before retrying...",
    "openai_general": "OpenAI API error: {}. Falling back to simplified processing.",
    "yahoo_finance": "Error fetching market data from Yahoo Finance: {}. Using fallback data.",
    "fred_api": "Error retrieving economic data from FRED: {}. Using cached or fallback values.",
    "general_api": "API call failed: {}. Using fallback mechanism."
}

# Fallback values for market data
MARKET_FALLBACKS = {
    "SPY": {"price": 450.0, "change": 0.0, "volume": 100000000},
    "QQQ": {"price": 380.0, "change": 0.0, "volume": 80000000},
    "BTC-USD": {"price": 60000.0, "change": 0.0, "volume": 30000000000},
    "ETH-USD": {"price": 3000.0, "change": 0.0, "volume": 15000000000}
}

# Common crypto mappings for standardization
CRYPTO_MAPPINGS = {
    # Full names to ticker
    'bitcoin': 'BTC-USD',
    'ethereum': 'ETH-USD',
    'cardano': 'ADA-USD',
    'dogecoin': 'DOGE-USD',
    'ripple': 'XRP-USD',
    'solana': 'SOL-USD',
    'polkadot': 'DOT-USD',
    'litecoin': 'LTC-USD',
    'chainlink': 'LINK-USD',
    
    # Short names to ticker
    'btc': 'BTC-USD',
    'eth': 'ETH-USD',
    'ada': 'ADA-USD',
    'doge': 'DOGE-USD',
    'xrp': 'XRP-USD',
    'sol': 'SOL-USD',
    'dot': 'DOT-USD',
    'ltc': 'LTC-USD',
    'link': 'LINK-USD',
    
    # Common ETFs and related stocks
    'gbtc': 'GBTC',
    'coin': 'COIN',
    'bito': 'BITO',
    'mstr': 'MSTR',  # MicroStrategy (holds BTC)
    'riot': 'RIOT',  # Mining company
    'mara': 'MARA'   # Mining company
}

# Global conversation storage
CONVERSATION_SESSIONS = {}

def standardize_crypto_ticker(ticker_or_text: str) -> str:
    """
    Standardize a crypto ticker or extract a crypto ticker from text.
    
    Args:
        ticker_or_text: A ticker symbol or text that might contain crypto references
        
    Returns:
        str: The standardized ticker symbol (like BTC-USD) or empty string if no crypto detected
    """
    if not ticker_or_text:
        return ""
    
    # If it's a simple ticker, standardize it directly
    ticker_clean = ticker_or_text.strip().upper()
    if ticker_clean in [k.upper() for k in CRYPTO_MAPPINGS.keys()]:
        # Find the case-insensitive match
        for k, v in CRYPTO_MAPPINGS.items():
            if k.upper() == ticker_clean:
                return v
    
    # For longer text, look for crypto keywords
    text_lower = ticker_or_text.lower()
    for keyword, ticker in CRYPTO_MAPPINGS.items():
        # Check for the keyword surrounded by word boundaries or beginning/end of string
        pattern = r'(^|\W)' + re.escape(keyword.lower()) + r'($|\W)'
        if re.search(pattern, text_lower):
            return ticker
    
    # No crypto references found
    return ""

def extract_tickers_from_text(text: str) -> list:
    """
    Extract potential ticker symbols from text.
    
    Args:
        text: Text to analyze for ticker symbols
        
    Returns:
        list: List of potential ticker symbols
    """
    if not text:
        return []
    
    # Look for standard ticker pattern (1-5 uppercase letters)
    ticker_pattern = r'\b[A-Z]{1,5}\b'
    ticker_matches = re.findall(ticker_pattern, text)
    
    # Filter out common English words often in ALL CAPS
    common_caps = {'I', 'A', 'THE', 'FOR', 'AND', 'OR', 'BUT', 'NOR', 'SO', 'YET', 'CEO', 'CFO', 'CTO', 'IPO'}
    tickers = [t for t in ticker_matches if t not in common_caps]
    
    # Try to find crypto references
    crypto_ticker = standardize_crypto_ticker(text)
    if crypto_ticker and crypto_ticker not in tickers:
        tickers.append(crypto_ticker)
    
    return tickers

def select_best_ticker(tickers: list, query_text: str = "", default_ticker: str = DEFAULT_MARKET_TICKER) -> str:
    """
    Select the most appropriate ticker from a list based on context.
    
    Args:
        tickers: List of potential ticker symbols
        query_text: Optional query text for additional context
        default_ticker: Default ticker to use if no tickers found
        
    Returns:
        str: The selected ticker symbol
    """
    if not tickers:
        return default_ticker
    
    # Check if we have crypto in the query
    if query_text:
        crypto_ticker = standardize_crypto_ticker(query_text)
        if crypto_ticker:
            return crypto_ticker
    
    # Prioritize crypto tickers if any
    for ticker in tickers:
        if '-USD' in ticker:
            return ticker
    
    # Otherwise return the first ticker
    return tickers[0]

def sanitize_text(text):
    """Remove emoji characters and other problematic Unicode characters from text"""
    try:
        # Try to encode the text to ascii and back to unicode, replacing unsupported chars
        return text.encode('ascii', 'replace').decode('ascii')
    except:
        # If that fails, use a more aggressive method to strip non-ascii chars
        return ''.join(char for char in text if ord(char) < 128)

def is_valid_market_query(query):
    """
    Determine if the input is a valid market event query.
    Returns True if it appears to be a proper question or detailed prompt.
    """
    # Reject empty or very short inputs
    if not query or len(query.strip()) < 3:
        return False
    
    # Check if it's a question (contains question mark or starts with question words)
    question_pattern = r'(what|how|when|why|did|does|will|can|could|would|should|is|are|was|were)'
    has_question_mark = '?' in query
    starts_with_question_word = re.match(question_pattern, query.lower().strip())
    
    # Check for specific market-related keywords
    market_keywords = [
        'market', 'stock', 'bond', 'etf', 'option', 'crypto', 'bitcoin', 'btc', 'ethereum', 'eth',
        'fed', 'fomc', 'inflation', 'cpi', 'gdp', 'unemployment', 'interest rate',
        'treasury', 'yield', 'economy', 'recession', 'bull', 'bear', 'rally',
        'crash', 'correction', 'volatility', 'earnings', 'dividend', 'nasdaq', 'dow',
        's&p', 'sp500', 'russell', 'price', 'trading', 'investment', 'portfolio',
        # Additional crypto-specific keywords
        'blockchain', 'altcoin', 'defi', 'mining', 'halving', 'token', 'wallet', 'exchange',
        'satoshi', 'binance', 'coinbase', 'gbtc', 'bito', 'sec', 'regulation', 'fork'
    ]
    
    # Expanded cryptocurrency tickers
    crypto_tickers = [
        'btc', 'eth', 'xrp', 'ltc', 'ada', 'dot', 'bnb', 'sol', 'doge', 'shib',
        'avax', 'matic', 'link', 'uni', 'usdt', 'usdc', 'dai', 'aave', 'comp'
    ]
    
    crypto_phrases = [
        'bitcoin etf', 'crypto etf', 'btc etf', 'bitcoin futures', 'blockchain technology',
        'crypto winter', 'bull run', 'bitcoin halving', 'crypto regulation',
        'digital asset', 'web3', 'nft', 'decentralized finance', 'defi protocol',
        'smart contract', 'bitcoin mining', 'ethereum 2.0', 'proof of stake',
        'bitcoin adoption', 'lightning network', 'crypto market'
    ]
    
    lower_query = query.lower()
    
    # Check if contains any market keyword
    contains_market_keyword = any(keyword in lower_query for keyword in market_keywords)
    
    # Check if contains any crypto ticker mentioned standalone (surrounded by spaces, punctuation, or at start/end)
    contains_crypto_ticker = False
    for ticker in crypto_tickers:
        # Check for ticker surrounded by non-alphanumeric characters or at beginning/end
        pattern = r'(^|[^a-zA-Z0-9])' + re.escape(ticker) + r'($|[^a-zA-Z0-9])'
        if re.search(pattern, lower_query):
            contains_crypto_ticker = True
            break
    
    # Check if contains any crypto phrase
    contains_crypto_phrase = any(phrase in lower_query for phrase in crypto_phrases)
    
    # Consider it valid if:
    # 1. It's a question (has question mark or starts with question word)
    # 2. OR it contains market keywords AND has enough context (longer than 10 chars)
    # 3. OR it specifically mentions crypto tickers or phrases
    is_valid = (
        (has_question_mark or starts_with_question_word) or 
        (contains_market_keyword and len(query.strip()) > 10) or
        contains_crypto_ticker or
        contains_crypto_phrase
    )
    
    # Debug info
    if not is_valid:
        print("\nQuery validation failed:")
        print(f"  Has question mark: {has_question_mark}")
        print(f"  Starts with question word: {bool(starts_with_question_word)}")
        print(f"  Contains market keyword: {contains_market_keyword}")
        print(f"  Contains crypto ticker: {contains_crypto_ticker}")
        print(f"  Contains crypto phrase: {contains_crypto_phrase}")
        print(f"  Length: {len(query.strip())} characters")
    
    return is_valid

def extract_date_from_query(user_input: str, parsed_event: str) -> tuple:
    """
    Extract date from a user query or LLM response about a historical event.
    Enhanced to handle relative dates and a wider range of date formats.
    
    Args:
        user_input: The user's query string
        parsed_event: The LLM's parsed interpretation of the event
        
    Returns:
        tuple: (extracted_date, ticker_symbol, event_description)
            - extracted_date: Date in 'YYYY-MM-DD' format or None if not found
            - ticker_symbol: Extracted ticker symbol or None
            - event_description: Brief description of the event
    """
    # Combine user input and parsed event for more context
    combined_text = f"{user_input} {parsed_event}"
    
    # Extract ticker symbols from the text
    ticker_symbols = extract_tickers_from_text(combined_text)
    
    # Select the most appropriate ticker
    ticker = select_best_ticker(ticker_symbols, combined_text, DEFAULT_MARKET_TICKER)
    
    # Get current date for relative date calculations
    current_date = datetime.now()
    
    # Try to extract absolute dates first (specific date mentions)
    date_result = extract_absolute_date(combined_text)
    if date_result:
        return date_result, ticker, combined_text
    
    # Try to extract relative dates if no absolute date found
    date_result = extract_relative_date(combined_text, current_date)
    if date_result:
        return date_result, ticker, combined_text
        
    # If no date found, return None with the ticker and text
    return None, ticker, combined_text

def extract_absolute_date(text: str) -> str:
    """
    Extract absolute date references from text.
    
    Args:
        text: Text to search for date references
        
    Returns:
        str: Date in YYYY-MM-DD format or None if not found
    """
    # Map month names to numbers
    month_map = {
        'january': 1, 'jan': 1,
        'february': 2, 'feb': 2,
        'march': 3, 'mar': 3,
        'april': 4, 'apr': 4,
        'may': 5,
        'june': 6, 'jun': 6,
        'july': 7, 'jul': 7,
        'august': 8, 'aug': 8,
        'september': 9, 'sep': 9,
        'october': 10, 'oct': 10,
        'november': 11, 'nov': 11,
        'december': 12, 'dec': 12
    }
    
    # Define date patterns for absolute dates
    date_patterns = [
        # Full dates (YYYY-MM-DD, Month DD YYYY, etc.)
        r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b',
        r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b',
        r'\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b',  # YYYY-MM-DD or YYYY/MM/DD
        r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b',  # DD-MM-YYYY or DD/MM/YYYY
        r'\b(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December),?\s+(\d{4})\b',
        r'\b(\d{1,2})(?:st|nd|rd|th)?\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?,?\s+(\d{4})\b',
        
        # Year + Month
        r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b',
        r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+(\d{4})\b',
        r'\b(\d{4})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\b',
        r'\b(\d{4})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\b',
        
        # Just year (with context words)
        r'\bin\s+(\d{4})\b',
        r'\bof\s+(\d{4})\b',
        r'\bduring\s+(\d{4})\b',
        r'\b(20\d{2})\b',  # Just years in the 2000s
        r'\b(19\d{2})\b',  # Just years in the 1900s
    ]
    
    # Try each date pattern until we find a match
    for pattern in date_patterns:
        matches = re.search(pattern, text, re.IGNORECASE)
        if matches:
            groups = matches.groups()
            
            # Process full date with month name (e.g., January 15, 2023)
            if len(groups) == 3 and any(month.lower() in month_map for month in [groups[0], groups[1]] if isinstance(month, str)):
                # Determine which group is the month
                month_group = groups[0] if groups[0].lower() in month_map else groups[1]
                month = month_map[month_group.lower()]
                
                # Determine which groups are day and year
                if groups[0].lower() in month_map:
                    # Format: Month Day Year
                    day = int(groups[1])
                    year = int(groups[2])
                else:
                    # Format: Day Month Year
                    day = int(groups[0])
                    year = int(groups[2])
                
                try:
                    # Validate the date
                    if 1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2100:
                        # Create the date with zero-padding for month and day
                        formatted_date = f"{year}-{month:02d}-{day:02d}"
                        return formatted_date
                except ValueError:
                    continue
                    
            # Process YYYY-MM-DD format
            elif len(groups) == 3 and groups[0].isdigit() and len(groups[0]) == 4:
                year = int(groups[0])
                month = int(groups[1])
                day = int(groups[2])
                try:
                    # Validate the date
                    if 1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2100:
                        formatted_date = f"{year}-{month:02d}-{day:02d}"
                        return formatted_date
                except ValueError:
                    continue
                    
            # Process DD-MM-YYYY format
            elif len(groups) == 3 and groups[2].isdigit() and len(groups[2]) == 4:
                day = int(groups[0])
                month = int(groups[1])
                year = int(groups[2])
                try:
                    # Validate the date
                    if 1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2100:
                        formatted_date = f"{year}-{month:02d}-{day:02d}"
                        return formatted_date
                except ValueError:
                    continue
                    
            # Process Month and year (e.g., January 2023)
            elif len(groups) == 2 and ((isinstance(groups[0], str) and groups[0].lower() in month_map) or 
                                        (isinstance(groups[1], str) and groups[1].lower() in month_map)):
                # Determine which group is the month and which is the year
                if isinstance(groups[0], str) and groups[0].lower() in month_map:
                    month = month_map[groups[0].lower()]
                    year = int(groups[1])
                else:
                    month = month_map[groups[1].lower()]
                    year = int(groups[0])
                    
                try:
                    # Validate and create date (default to the 1st of the month)
                    if 1 <= month <= 12 and 1900 <= year <= 2100:
                        formatted_date = f"{year}-{month:02d}-01"
                        return formatted_date
                except ValueError:
                    continue
                    
            # Process just year (e.g., 2023, 1987)
            elif len(groups) == 1 and groups[0].isdigit() and (1900 <= int(groups[0]) <= 2100):
                year = int(groups[0])
                # Default to January 1st
                formatted_date = f"{year}-01-01"
                return formatted_date
                
    # No absolute date found
    return None

def extract_relative_date(text: str, reference_date: datetime) -> str:
    """
    Extract relative date references and convert them to absolute dates.
    
    Args:
        text: Text to search for relative date references
        reference_date: Reference date for relative calculations
        
    Returns:
        str: Date in YYYY-MM-DD format or None if not found
    """
    # Common time periods in singular and plural forms
    time_units = {
        'day': 1, 'days': 1,
        'week': 7, 'weeks': 7,
        'month': 30, 'months': 30,  # Approximate
        'year': 365, 'years': 365,  # Approximate
        'quarter': 90, 'quarters': 90,  # Approximate
    }
    
    # Pattern for "X time_unit(s) ago"
    ago_pattern = r'\b(\d+)\s+(day|days|week|weeks|month|months|year|years|quarter|quarters)\s+ago\b'
    ago_matches = re.search(ago_pattern, text, re.IGNORECASE)
    if ago_matches:
        quantity = int(ago_matches.group(1))
        unit = ago_matches.group(2).lower()
        days_to_subtract = quantity * time_units[unit]
        target_date = reference_date - timedelta(days=days_to_subtract)
        return target_date.strftime("%Y-%m-%d")
    
    # Pattern for "last X" or "past X" (where X is a time unit)
    last_pattern = r'\b(last|past)\s+(day|days|week|weeks|month|months|year|years|quarter|quarters)\b'
    last_matches = re.search(last_pattern, text, re.IGNORECASE)
    if last_matches:
        unit = last_matches.group(2).lower()
        days_to_subtract = time_units[unit.rstrip('s')]  # Use singular form for lookup
        target_date = reference_date - timedelta(days=days_to_subtract)
        return target_date.strftime("%Y-%m-%d")
    
    # Pattern for "last X months/years" as a number
    last_n_pattern = r'\b(last|past)\s+(\d+)\s+(day|days|week|weeks|month|months|year|years|quarter|quarters)\b'
    last_n_matches = re.search(last_n_pattern, text, re.IGNORECASE)
    if last_n_matches:
        quantity = int(last_n_matches.group(2))
        unit = last_n_matches.group(3).lower()
        days_to_subtract = quantity * time_units[unit]
        target_date = reference_date - timedelta(days=days_to_subtract)
        return target_date.strftime("%Y-%m-%d")
    
    # Pattern for "early/mid/late year" (e.g., "early 2022", "late 1990s")
    period_year_pattern = r'\b(early|mid|late)\s+(20\d{2}|19\d{2}|2000s|1900s|90s|80s|70s|60s|50s|40s|30s|20s|10s)\b'
    period_year_matches = re.search(period_year_pattern, text, re.IGNORECASE)
    if period_year_matches:
        period = period_year_matches.group(1).lower()
        year_ref = period_year_matches.group(2).lower()
        
        # Handle decade references (90s, 2000s, etc.)
        if year_ref.endswith('s'):
            # Extract the decade
            if year_ref.startswith('20') or year_ref.startswith('19'):
                # e.g., 2000s, 1990s
                decade_start = int(year_ref[:4])
            else:
                # e.g., 90s = 1990s, 00s = 2000s
                prefix = '19' if int(year_ref[:-1]) >= 10 else '20'
                decade_start = int(f"{prefix}{year_ref[:-1]}0")
            
            # Define early/mid/late within the decade
            if period == 'early':
                year = decade_start
                month = 1
            elif period == 'mid':
                year = decade_start + 5
                month = 6
            else:  # late
                year = decade_start + 9
                month = 12
        else:
            # It's a specific year (e.g., 2022)
            year = int(year_ref)
            
            # Define early/mid/late within the year
            if period == 'early':
                month = 2
            elif period == 'mid':
                month = 6
            else:  # late
                month = 11
        
        # Return formatted date
        return f"{year}-{month:02d}-01"
    
    # Pattern for "beginning/end of year" (e.g., "beginning of 2020")
    begin_end_pattern = r'\b(beginning|start|end)\s+of\s+(20\d{2}|19\d{2})\b'
    begin_end_matches = re.search(begin_end_pattern, text, re.IGNORECASE)
    if begin_end_matches:
        position = begin_end_matches.group(1).lower()
        year = int(begin_end_matches.group(2))
        
        if position in ['beginning', 'start']:
            return f"{year}-01-01"
        else:  # end
            return f"{year}-12-31"
    
    # Pattern for "Q1/Q2/Q3/Q4 YYYY" (quarters)
    quarter_pattern = r'\bQ([1-4])\s+(20\d{2}|19\d{2})\b'
    quarter_matches = re.search(quarter_pattern, text, re.IGNORECASE)
    if quarter_matches:
        quarter = int(quarter_matches.group(1))
        year = int(quarter_matches.group(2))
        
        month = 3 * quarter - 2  # Q1->1, Q2->4, Q3->7, Q4->10
        return f"{year}-{month:02d}-01"
    
    # Pattern for named events with known dates
    events = {
        'covid pandemic start': '2020-03-11',  # WHO declaration date
        'covid lockdown': '2020-03-15',  # Approximate US lockdown start
        'global financial crisis': '2008-09-15',  # Lehman Brothers bankruptcy
        'dot com bubble burst': '2000-03-10',  # NASDAQ peak
        'black monday': '1987-10-19',
        'nine eleven': '2001-09-11',
        '9/11': '2001-09-11',
        'housing market crash': '2008-09-15',  # Using Lehman as reference
        'great recession': '2008-09-15',
        'brexit referendum': '2016-06-23',
        'brexit vote': '2016-06-23',
        'trump election': '2016-11-08',
        'biden election': '2020-11-03',
        'gamestop short squeeze': '2021-01-27',
        'bitcoin halving 2020': '2020-05-11',
        'bitcoin halving 2016': '2016-07-09',
        'eth merge': '2022-09-15',
        'ethereum merge': '2022-09-15',
        'ethereum london fork': '2021-08-05',
        'ftx collapse': '2022-11-11',
        'svb failure': '2023-03-10',
        'silicon valley bank failure': '2023-03-10',
        'credit suisse collapse': '2023-03-19',
    }
    
    # Check for references to known events
    text_lower = text.lower()
    for event, date in events.items():
        if event in text_lower:
            return date
    
    # No relative date found
    return None

def get_historical_macro_data(target_date: str) -> dict:
    """
    Retrieve macroeconomic data from the time period closest to the specified date.
    
    Args:
        target_date: Date in YYYY-MM-DD format
        
    Returns:
        dict: Historical macroeconomic indicators
    """
    if not fred or not FRED_API_KEY:
        print(f"Warning: FRED API key not available. Using fallback values for historical macro data.")
        return {k: v for k, v in FALLBACK_VALUES.items()}
    
    try:
        # Convert target date to datetime
        target_dt = datetime.strptime(target_date, "%Y-%m-%d")
        
        # Initialize result dictionary
        historical_macro = {}
        found_count = 0
        missing_count = 0
        
        # Define how far back to look for data (1 year)
        max_lookback = 365
        
        print(f"Fetching historical macroeconomic data for {target_date}...")
        
        # Process each FRED metric
        for metric_name, series_id in FRED_METRICS.items():
            try:
                # Get the series data around the target date
                lookback_date = (target_dt - timedelta(days=max_lookback)).strftime("%Y-%m-%d")
                series = fred.get_series(series_id, observation_start=lookback_date, observation_end=target_date)
                
                if series.empty:
                    # If no data available before target date, use fallback
                    historical_macro[metric_name] = FALLBACK_VALUES.get(metric_name, 0.0)
                    print(f"  No historical data for {metric_name} ({series_id}), using fallback")
                    missing_count += 1
                else:
                    # Get the closest available data point to the target date
                    # Sort by date (index) descending to get most recent first
                    sorted_series = series.sort_index(ascending=False)
                    closest_value = sorted_series.iloc[0]
                    closest_date = sorted_series.index[0].strftime("%Y-%m-%d")
                    
                    # Handle special cases where we need annual percentage change
                    if metric_name in ["CPI_YoY", "CoreCPI", "CorePCE"]:
                        # For inflation metrics, we need to calculate year-over-year change
                        if len(sorted_series) >= 13:  # Make sure we have at least a year of data
                            latest_value = sorted_series.iloc[0]
                            year_ago_value = sorted_series.iloc[12]  # Approximately 1 year ago (12 months)
                            yoy_pct_change = ((latest_value / year_ago_value) - 1) * 100
                            historical_macro[metric_name] = round(yoy_pct_change, 1)
                            print(f"  {metric_name}: {historical_macro[metric_name]:.1f}% (calculated from {closest_date})")
                        else:
                            # Not enough data for YoY calculation
                            historical_macro[metric_name] = FALLBACK_VALUES.get(metric_name, 0.0)
                            print(f"  Not enough historical data for {metric_name} YoY calculation")
                            missing_count += 1
                    else:
                        # For other metrics, use the value directly
                        historical_macro[metric_name] = float(closest_value)
                        print(f"  {metric_name}: {historical_macro[metric_name]:.2f} (from {closest_date})")
                    
                    found_count += 1
                    
            except Exception as e:
                print(f"  Error fetching historical data for {metric_name}: {str(e)}")
                historical_macro[metric_name] = FALLBACK_VALUES.get(metric_name, 0.0)
                missing_count += 1
        
        # Add backward compatibility fields
        if "FedFundsRate" in historical_macro and "Fed_Funds_Rate" not in historical_macro:
            historical_macro["Fed_Funds_Rate"] = historical_macro["FedFundsRate"]
        
        # Add metadata
        historical_macro["_timestamp"] = target_date
        historical_macro["_data_source"] = "fred_historical"
        historical_macro["_metrics_found"] = found_count
        historical_macro["_metrics_missing"] = missing_count
        historical_macro["_live_percentage"] = 100 * (found_count / (found_count + missing_count)) if (found_count + missing_count) > 0 else 0
        
        print(f"Found {found_count} historical metrics, {missing_count} missing/fallback")
        return historical_macro
        
    except Exception as e:
        print(f"Error retrieving historical macro data: {str(e)}")
        return {k: v for k, v in FALLBACK_VALUES.items()}

def analyze_historical_event(event_date: str, ticker: str, days_to_analyze: int = 30) -> dict:
    """
    Analyze market data for a specific historical event.
    
    Args:
        event_date: Date of the event in YYYY-MM-DD format
        ticker: Ticker symbol to analyze
        days_to_analyze: Number of days after the event to analyze
        
    Returns:
        dict: Analysis results including price changes and market data
    """
    if not event_date:
        return {
            "success": False,
            "error": "No event date provided"
        }
    
    try:
        # Calculate end date
        event_dt = datetime.strptime(event_date, "%Y-%m-%d")
        end_dt = event_dt + timedelta(days=days_to_analyze)
        end_date = end_dt.strftime("%Y-%m-%d")
        
        # Get historical macroeconomic data for the event date
        try:
            historical_macro = get_historical_macro_data(event_date)
            print(f"✓ Successfully retrieved historical macro data for {event_date}")
        except Exception as e:
            print(f"⚠️ Error retrieving historical macro data: {str(e)}")
            print("   Using fallback macro values.")
            historical_macro = {k: v for k, v in FALLBACK_VALUES.items()}
            historical_macro["_timestamp"] = event_date
            historical_macro["_data_source"] = "fallback_values"
            historical_macro["_metrics_found"] = 0
            historical_macro["_metrics_missing"] = len(FALLBACK_VALUES)
            historical_macro["_live_percentage"] = 0
        
        # Standardize the ticker before fetching market data
        # Use our standardization function for consistent handling
        crypto_ticker = standardize_crypto_ticker(ticker)
        if crypto_ticker:
            ticker = crypto_ticker
        
        # Fetch market data with error handling
        try:
            df = fetch_market_data(ticker, event_date, end_date)
            
            if df.empty:
                # Handle cryptocurrencies specially
                if any(crypto_prefix in ticker for crypto_prefix in ['BTC', 'ETH', 'XRP', 'LTC']):
                    fallback_ticker = 'BTC-USD'  # Use BTC as a proxy for crypto market
                    print(f"⚠️ No data for {ticker}. Trying fallback ticker {fallback_ticker}...")
                    df = fetch_market_data(fallback_ticker, event_date, end_date)
                    if not df.empty:
                        ticker = fallback_ticker
                        print(f"✓ Using {ticker} as proxy for crypto market")
                
                # If still empty, try with a broader market ticker
                if df.empty and ticker != 'SPY':
                    fallback_ticker = 'SPY'  # Use SPY as general market proxy
                    print(f"⚠️ No data for {ticker}. Trying market index {fallback_ticker}...")
                    df = fetch_market_data(fallback_ticker, event_date, end_date)
                    if not df.empty:
                        ticker = fallback_ticker
                        print(f"✓ Using {ticker} as general market proxy")
                
                # If still no data, return an error with the historical macro data
                if df.empty:
                    return {
                        "success": False,
                        "error": f"No market data available for {ticker} from {event_date} to {end_date}",
                        "macro_data": historical_macro,
                        "attempted_tickers": [ticker]
                    }
        except Exception as e:
            print(f"⚠️ Error fetching market data: {str(e)}")
            return {
                "success": False,
                "error": f"Error fetching market data: {str(e)}",
                "macro_data": historical_macro
            }
        
        # Calculate price changes
        overall_change_pct, max_drawdown_pct = calculate_price_changes(df)
        
        # Get actual date range from the data
        actual_start_date = df.index[0].strftime("%Y-%m-%d")
        actual_end_date = df.index[-1].strftime("%Y-%m-%d")
        date_range = f"{actual_start_date} to {actual_end_date}"
        
        # Extract key price data
        first_price = float(df['Close'].iloc[0])
        last_price = float(df['Close'].iloc[-1])
        highest_price = float(df['High'].max())
        lowest_price = float(df['Low'].min())
        
        # Calculate volatility (standard deviation of daily returns)
        daily_returns = df['Close'].pct_change().dropna()
        volatility = float(daily_returns.std() * 100)  # Convert to percentage
        
        # Prepare detailed formula values for later display
        price_change_formula = {
            "start_price": first_price,
            "end_price": last_price,
            "calculation": "((end_price / start_price) - 1) * 100"
        }
        
        max_drawdown_formula = {
            "highest_price": highest_price,
            "lowest_price": lowest_price,
            "calculation": "((lowest_price / highest_price) - 1) * 100"
        }
        
        volatility_formula = {
            "daily_returns_std": daily_returns.std(),
            "calculation": "standard_deviation(daily_returns) * 100"
        }
        
        # Determine if trend is bullish or bearish
        trend = "Bullish" if overall_change_pct > 0 else "Bearish"
        
        # Prepare result
        result = {
            "success": True,
            "ticker": ticker,
            "event_date": event_date,
            "date_range_analyzed": date_range,
            "days_analyzed": len(df),
            "price_change_pct": round(overall_change_pct, 2),
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "start_price": round(first_price, 2),
            "end_price": round(last_price, 2),
            "highest_price": round(highest_price, 2),
            "lowest_price": round(lowest_price, 2),
            "volatility_pct": round(volatility, 2),
            "macro_data": historical_macro
        }
        
        # Generate impact explanation and add it to the result
        impact_explanation = generate_event_impact_explanation(result)
        if impact_explanation.get("success", False):
            result["impact_explanation"] = impact_explanation
        
        # Add sentiment comparison analysis
        result = add_sentiment_comparison_to_analysis(result)
        
        return result
        
    except Exception as e:
        print(f"⚠️ Error in historical event analysis: {str(e)}")
        return {
            "success": False,
            "error": f"Error analyzing historical event: {str(e)}",
            "macro_data": FALLBACK_VALUES
        }

def generate_event_impact_explanation(event_details: dict, similar_events=None) -> dict:
    """
    Generate a narrative explanation of how a historical event impacted the market.
    
    Args:
        event_details: Dictionary containing historical event analysis
        similar_events: Optional list of similar historical events for context
        
    Returns:
        dict: Explanation of market impact with causal relationships
    """
    # Check if we have valid event details
    if not event_details or not event_details.get("success", False):
        return {
            "success": False,
            "message": "Insufficient data to explain market impact"
        }
    
    # Extract key metrics for analysis
    event_date = event_details.get("event_date", "Unknown date")
    ticker = event_details.get("ticker", "the market")
    price_change_pct = event_details.get("price_change_pct", 0)  # Changed variable name to match the key
    max_drawdown = event_details.get("max_drawdown_pct", 0)
    volatility = event_details.get("volatility_pct", 0)
    trend = event_details.get("trend", "Neutral")
    start_price = event_details.get("start_price", 0)
    end_price = event_details.get("end_price", 0)
    days_analyzed = event_details.get("days_analyzed", 0)
    
    # Get macro environment data
    macro_data = event_details.get("macro_data", {})
    
    # Prepare explanation sections
    immediate_reaction = ""
    explanation = ""
    follow_on_effects = ""
    macro_context = ""
    
    # Generate immediate market reaction description
    if abs(price_change_pct) < 1:  # Use price_change_pct instead of price_change
        immediate_reaction = f"{ticker} showed minimal movement initially"
    elif abs(price_change_pct) < 3:  # Use price_change_pct instead of price_change
        immediate_reaction = f"{ticker} moved {'upward' if price_change_pct > 0 else 'downward'} slightly"
    elif abs(price_change_pct) < 7:  # Use price_change_pct instead of price_change
        immediate_reaction = f"{ticker} responded with a {'notable rise' if price_change_pct > 0 else 'notable decline'}"
    else:
        immediate_reaction = f"{ticker} experienced a {'significant rally' if price_change_pct > 0 else 'significant sell-off'}"
    
    # Add volatility context
    if volatility > 40:
        immediate_reaction += f" with extreme volatility ({volatility:.1f}%)"
    elif volatility > 25:
        immediate_reaction += f" with high volatility ({volatility:.1f}%)"
    elif volatility > 15:
        immediate_reaction += f" with increased volatility ({volatility:.1f}%)"
    
    # Generate explanation based on price action
    if price_change_pct > 0:  # Use price_change_pct instead of price_change
        if max_drawdown < 3:
            explanation = f"The market showed strong confidence in response to this event, with {ticker} steadily climbing from ${start_price} to ${end_price} over {days_analyzed} trading days with minimal pullbacks."
        elif max_drawdown < 10:
            explanation = f"Despite some normal pullbacks (maximum drawdown of {max_drawdown}%), {ticker} showed overall strength following this event, rising from ${start_price} to ${end_price} over {days_analyzed} trading days."
        else:
            explanation = f"The market reaction was volatile but ultimately positive. {ticker} experienced significant pullbacks (maximum drawdown of {max_drawdown}%) but still closed up from ${start_price} to ${end_price} over the analyzed period."
    else:
        if abs(max_drawdown) < 5:
            explanation = f"The market responded negatively but in an orderly fashion, with {ticker} declining gradually from ${start_price} to ${end_price} over {days_analyzed} trading days."
        elif abs(max_drawdown) < 15:
            explanation = f"The event triggered selling pressure, with {ticker} falling from ${start_price} to ${end_price}, experiencing a maximum drawdown of {max_drawdown}% during the {days_analyzed}-day period."
        else:
            explanation = f"The market reacted very negatively, with {ticker} experiencing a significant sell-off from ${start_price} to ${end_price} and a severe maximum drawdown of {max_drawdown}% during the period."
    
    # Add follow-on effects based on trend development
    day_descriptor = "month" if days_analyzed >= 20 else "period"
    if price_change_pct > 5:  # Use price_change_pct instead of price_change
        follow_on_effects = f"The strong positive reaction suggests the event was perceived as very bullish for {ticker}, leading to sustained buying interest throughout the {day_descriptor}."
    elif price_change_pct > 0:  # Use price_change_pct instead of price_change
        follow_on_effects = f"The positive but measured reaction suggests the market viewed this event as constructive but not transformative for {ticker}."
    elif price_change_pct > -5:  # Use price_change_pct instead of price_change
        follow_on_effects = f"The mild negative reaction suggests some caution or disappointment, but not significant concern about {ticker}'s prospects."
    else:
        follow_on_effects = f"The strong negative reaction suggests the event was perceived as significantly bearish for {ticker}, leading to persistent selling throughout the {day_descriptor}."
    
    # Add macro environment context
    if macro_data:
        cpi = macro_data.get("CPI_YoY", None)
        fed_rate = macro_data.get("FedFundsRate", None)
        unemployment = macro_data.get("Unemployment", None)
        yield_curve = (macro_data.get("TenYearYield", 0) - macro_data.get("TwoYearYield", 0))
        
        macro_factors = []
        if cpi is not None:
            inflation_desc = "high" if cpi > 4 else "moderate" if cpi > 2 else "low"
            macro_factors.append(f"inflation was {inflation_desc} ({cpi:.1f}%)")
        
        if fed_rate is not None:
            rate_desc = "restrictive" if fed_rate > 4 else "neutral" if fed_rate > 2 else "accommodative"
            macro_factors.append(f"Fed policy was {rate_desc} ({fed_rate:.2f}%)")
        
        if unemployment is not None:
            employment_desc = "tight" if unemployment < 4 else "balanced" if unemployment < 6 else "weak"
            macro_factors.append(f"labor market was {employment_desc} ({unemployment:.1f}% unemployment)")
        
        if yield_curve is not None:
            curve_desc = "inverted" if yield_curve < 0 else "flat" if yield_curve < 0.5 else "positively sloped"
            macro_factors.append(f"yield curve was {curve_desc} ({yield_curve:.2f}%)")
        
        if macro_factors:
            macro_context = "This market reaction occurred in a macroeconomic environment where " + ", ".join(macro_factors[:3]) + "."
            
            # Add interpretation
            if price_change_pct > 0 and cpi and cpi > 4:  # Use price_change_pct instead of price_change
                macro_context += f" The positive market reaction despite high inflation suggests the event was seen as outweighing inflation concerns."
            elif price_change_pct < 0 and yield_curve and yield_curve < 0:  # Use price_change_pct instead of price_change
                macro_context += f" The negative market reaction in an inverted yield curve environment suggests amplified recession concerns."
    
    # Combine all sections
    full_explanation = {
        "success": True,
        "immediate_reaction": immediate_reaction,
        "causal_explanation": explanation,
        "follow_on_effects": follow_on_effects,
        "macro_context": macro_context,
        "summary": f"{immediate_reaction}. {explanation} {follow_on_effects}".strip()
    }
    
    # Add comparative analysis with similar events if available
    if similar_events and len(similar_events) > 0:
        similar_events_summary = []
        similar_events_count = len(similar_events)
        similar_positive_count = sum(1 for e in similar_events if e.get('price_change_pct', 0) > 0)
        similar_negative_count = similar_events_count - similar_positive_count
        
        consistency = max(similar_positive_count, similar_negative_count) / similar_events_count if similar_events_count > 0 else 0
        
        # Generate comparative insight
        if consistency >= 0.8:
            direction = "positive" if similar_positive_count > similar_negative_count else "negative"
            similar_events_summary.append(f"This market reaction is highly consistent with historical patterns, as {int(consistency*100)}% of similar events also showed {direction} price action.")
        elif consistency >= 0.6:
            direction = "positive" if similar_positive_count > similar_negative_count else "negative"
            similar_events_summary.append(f"This market reaction is moderately consistent with historical patterns, with {int(consistency*100)}% of similar events showing {direction} price action.")
        else:
            similar_events_summary.append(f"This market reaction shows mixed consistency with historical patterns ({similar_positive_count} positive vs {similar_negative_count} negative outcomes in similar events).")
        
        # Add comparison to event's price change vs average
        avg_change = sum(e.get('price_change_pct', 0) for e in similar_events) / similar_events_count
        if abs(price_change_pct - avg_change) < 2:  # Use price_change_pct instead of price_change
            similar_events_summary.append(f"The magnitude of price change ({price_change_pct:.1f}%) was very close to the historical average ({avg_change:.1f}%) for similar events.")
        elif price_change_pct > avg_change:  # Use price_change_pct instead of price_change
            similar_events_summary.append(f"The price change ({price_change_pct:.1f}%) was stronger than the historical average ({avg_change:.1f}%) for similar events, suggesting amplified market sensitivity.")
        else:
            similar_events_summary.append(f"The price change ({price_change_pct:.1f}%) was weaker than the historical average ({avg_change:.1f}%) for similar events, suggesting diminished market sensitivity.")
        
        full_explanation["historical_pattern_analysis"] = " ".join(similar_events_summary)
    
    return full_explanation

def analyze_similar_events(similar_events: list) -> dict:
    """
    Analyze patterns in similar historical events to extract insights,
    including correlation between macro environments and market performance.
    
    Args:
        similar_events: List of similar historical events
        
    Returns:
        dict: Analysis of patterns across similar events, including macro correlations
    """
    if not similar_events:
        return {"success": False, "message": "No similar events found"}
    
    try:
        # Initialize counters and data collection
        total_events = len(similar_events)
        price_changes = []
        drawdowns = []
        bullish_count = 0
        bearish_count = 0
        sectors = {}
        tickers = {}
        avg_days_to_recovery = 0
        has_recovery_data = 0
        
        # For macro correlation analysis
        macro_data_points = []
        events_with_macro = 0
        
        # For sentiment analysis comparison
        sentiment_alignments = []
        events_with_sentiment = 0
        classified_vs_historical = {"aligned": 0, "divergent": 0}
        
        # Process each similar event
        for event in similar_events:
            # Extract price change and determine if bullish or bearish
            price_change = event.get('price_change_pct')
            if isinstance(price_change, (int, float)):
                price_changes.append(price_change)
                if price_change > 0:
                    bullish_count += 1
                else:
                    bearish_count += 1
            
            # Extract maximum drawdown
            drawdown = event.get('max_drawdown_pct')
            if isinstance(drawdown, (int, float)):
                drawdowns.append(drawdown)
            
            # Track sectors and tickers
            sector = event.get('sector', 'Unknown')
            if sector in sectors:
                sectors[sector] += 1
            else:
                sectors[sector] = 1
                
            ticker = event.get('affected_ticker', 'Unknown')
            if ticker in tickers:
                tickers[ticker] += 1
            else:
                tickers[ticker] = 1
            
            # Track recovery time if available
            if event.get('days_to_recovery'):
                avg_days_to_recovery += event.get('days_to_recovery')
                has_recovery_data += 1
                
            # Collect macro data if available for correlation analysis
            if 'macro_data' in event and event.get('price_change_pct') is not None:
                macro = event.get('macro_data', {})
                
                # Only include events that have at least some key macro metrics
                if any(key in macro for key in ['CPI_YoY', 'FedFundsRate', 'Unemployment', 'TenYearYield']):
                    macro_point = {
                        'price_change': event.get('price_change_pct'),
                        'date': event.get('event_date', 'Unknown'),
                        'cpi': macro.get('CPI_YoY'),
                        'fed_rate': macro.get('FedFundsRate'),
                        'unemployment': macro.get('Unemployment'),
                        'ten_year': macro.get('TenYearYield'),
                        'two_year': macro.get('TwoYearYield'),
                        'yield_curve': (macro.get('TenYearYield', 0) - macro.get('TwoYearYield', 0)) 
                            if 'TenYearYield' in macro and 'TwoYearYield' in macro else None
                    }
                    macro_data_points.append(macro_point)
                    events_with_macro += 1
            
            # Track sentiment data and alignment if available
            if 'sentiment_analysis' in event:
                events_with_sentiment += 1
                sentiment_data = event.get('sentiment_analysis', {})
                
                # Check if classified sentiment aligns with historical sentiment
                classified = sentiment_data.get('classified_sentiment', {}).get('label', 'Neutral')
                historical = sentiment_data.get('historical_sentiment', {}).get('label', 'Neutral')
                
                # Get alignment information
                alignment = sentiment_data.get('comparison', {}).get('agreement', 0)
                if alignment >= 0.7:  # Strong or perfect agreement
                    classified_vs_historical["aligned"] += 1
                else:
                    classified_vs_historical["divergent"] += 1
                
                # Add to alignments list
                sentiment_alignments.append({
                    'event_date': event.get('event_date', 'Unknown'),
                    'ticker': event.get('affected_ticker', 'Unknown'),
                    'classified': classified,
                    'historical': historical,
                    'alignment': alignment,
                    'price_change': event.get('price_change_pct')
                })
        
        # Calculate averages and trends
        avg_price_change = sum(price_changes) / len(price_changes) if price_changes else 0
        avg_drawdown = sum(drawdowns) / len(drawdowns) if drawdowns else 0
        
        if has_recovery_data > 0:
            avg_days_to_recovery /= has_recovery_data
        
        # Calculate consistency score (0-100%)
        majority = max(bullish_count, bearish_count)
        consistency_score = (majority / total_events) * 100 if total_events > 0 else 0
        
        # Determine dominant sector and ticker
        dominant_sector = max(sectors.items(), key=lambda x: x[1])[0] if sectors else "Unknown"
        dominant_ticker = max(tickers.items(), key=lambda x: x[1])[0] if tickers else "Unknown"
        
        # Determine overall pattern
        if avg_price_change > 5:
            pattern = "Strong bullish trend"
        elif avg_price_change > 1:
            pattern = "Moderate bullish trend"
        elif avg_price_change > -1:
            pattern = "Neutral or sideways movement"
        elif avg_price_change > -5:
            pattern = "Moderate bearish trend"
        else:
            pattern = "Strong bearish trend"
        
        # Add detail about drawdowns to the pattern
        if avg_drawdown > 10:
            pattern += " with significant volatility"
        elif avg_drawdown > 5:
            pattern += " with moderate volatility"
        else:
            pattern += " with low volatility"
        
        # Create the result with basic pattern analysis
        result = {
            "success": True,
            "pattern_summary": pattern,
            "consistency_score": round(consistency_score),
            "avg_price_change": round(avg_price_change, 2),
            "avg_max_drawdown": round(avg_drawdown, 2),
            "bullish_pct": round((bullish_count / total_events) * 100) if total_events > 0 else 0,
            "bearish_pct": round((bearish_count / total_events) * 100) if total_events > 0 else 0,
            "dominant_sector": dominant_sector,
            "dominant_ticker": dominant_ticker,
            "avg_days_to_recovery": round(avg_days_to_recovery) if has_recovery_data > 0 else "Unknown",
            "similar_events_count": total_events
        }
        
        # Calculate macro correlations if we have enough data points
        if events_with_macro >= 3:  # Need at least 3 data points for meaningful correlation
            macro_correlations = calculate_macro_correlations(macro_data_points)
            macro_insights = generate_macro_insights(macro_correlations)
            
            result["has_macro_analysis"] = True
            result["events_with_macro"] = events_with_macro
            result["macro_correlations"] = macro_correlations
            result["macro_insights"] = macro_insights
        else:
            result["has_macro_analysis"] = False
            
        # Add sentiment analysis comparison if we have enough data points
        if events_with_sentiment >= 2:  # Need at least 2 events with sentiment data
            # Calculate the percentage of events where classified sentiment aligned with historical sentiment
            alignment_pct = (classified_vs_historical["aligned"] / events_with_sentiment * 100) if events_with_sentiment > 0 else 0
            
            # Analyze performance when sentiment aligned vs diverged
            aligned_performance = []
            diverged_performance = []
            
            for alignment_data in sentiment_alignments:
                if alignment_data.get('alignment', 0) >= 0.7:
                    if isinstance(alignment_data.get('price_change'), (int, float)):
                        aligned_performance.append(alignment_data['price_change'])
                else:
                    if isinstance(alignment_data.get('price_change'), (int, float)):
                        diverged_performance.append(alignment_data['price_change'])
            
            # Calculate average performance for aligned vs diverged events
            avg_aligned_performance = sum(aligned_performance) / len(aligned_performance) if aligned_performance else 0
            avg_diverged_performance = sum(diverged_performance) / len(diverged_performance) if diverged_performance else 0
            
            # Generate insights based on sentiment alignment patterns
            sentiment_insights = []
            
            # Check if aligned sentiment is a better predictor
            performance_diff = abs(avg_aligned_performance) - abs(avg_diverged_performance)
            
            if len(aligned_performance) >= 2 and len(diverged_performance) >= 2:
                if performance_diff > 2:
                    sentiment_insights.append(
                        f"Events where sentiment analysis aligned with historical sentiment had stronger price movements "
                        f"({avg_aligned_performance:.1f}% vs {avg_diverged_performance:.1f}%)"
                    )
                elif performance_diff < -2:
                    sentiment_insights.append(
                        f"Events where sentiment analysis diverged from historical sentiment had stronger price movements "
                        f"({avg_diverged_performance:.1f}% vs {avg_aligned_performance:.1f}%)"
                    )
            
            # Check if high alignment percentage is meaningful
            if alignment_pct >= 70:
                sentiment_insights.append(
                    f"Strong consistency ({alignment_pct:.0f}%) between price-based classification and historical sentiment data "
                    f"suggests reliable sentiment signals for these events"
                )
            elif alignment_pct <= 30:
                sentiment_insights.append(
                    f"Low consistency ({alignment_pct:.0f}%) between price-based classification and historical sentiment data "
                    f"suggests sentiment often diverges from price action for these events"
                )
            
            # Add sentiment analysis to the result
            result["has_sentiment_analysis"] = True
            result["events_with_sentiment"] = events_with_sentiment
            result["sentiment_alignment_pct"] = round(alignment_pct)
            result["sentiment_insights"] = sentiment_insights
            
            # Add performance comparison
            if aligned_performance and diverged_performance:
                result["sentiment_performance"] = {
                    "aligned_sentiment_avg_price_change": round(avg_aligned_performance, 2),
                    "diverged_sentiment_avg_price_change": round(avg_diverged_performance, 2),
                    "aligned_count": len(aligned_performance),
                    "diverged_count": len(diverged_performance)
                }
        else:
            result["has_sentiment_analysis"] = False
        
        return result
        
    except Exception as e:
        print(f"⚠️ Error in similar events analysis: {str(e)}")
        return {
            "success": False,
            "message": f"Error analyzing similar events: {str(e)}"
        }

def calculate_macro_correlations(macro_data_points: list) -> dict:
    """
    Calculate correlations between macroeconomic factors and market performance.
    
    Args:
        macro_data_points: List of dictionaries with macro data and price changes
        
    Returns:
        dict: Correlations between macro factors and price changes
    """
    # Initialize correlation results
    correlations = {
        'cpi': {'correlation': 0, 'strength': 'None', 'sample_size': 0},
        'fed_rate': {'correlation': 0, 'strength': 'None', 'sample_size': 0},
        'unemployment': {'correlation': 0, 'strength': 'None', 'sample_size': 0},
        'yield_curve': {'correlation': 0, 'strength': 'None', 'sample_size': 0}
    }
    
    try:
        # Calculate correlations for each factor
        for factor in ['cpi', 'fed_rate', 'unemployment', 'yield_curve']:
            # Get valid data points (where both price_change and the factor are not None)
            valid_points = [(p['price_change'], p[factor]) 
                            for p in macro_data_points 
                            if p['price_change'] is not None and p[factor] is not None]
            
            # Need at least 3 points for correlation
            if len(valid_points) >= 3:
                # Extract x and y values for correlation
                x_values = [p[0] for p in valid_points]  # price changes
                y_values = [p[1] for p in valid_points]  # macro factor values
                
                # Calculate Pearson correlation coefficient
                n = len(valid_points)
                sum_x = sum(x_values)
                sum_y = sum(y_values)
                sum_xy = sum(x*y for x, y in zip(x_values, y_values))
                sum_x2 = sum(x*x for x in x_values)
                sum_y2 = sum(y*y for y in y_values)
                
                # Calculate correlation coefficient
                numerator = n * sum_xy - sum_x * sum_y
                denominator = ((n * sum_x2 - sum_x ** 2) * (n * sum_y2 - sum_y ** 2)) ** 0.5
                
                if denominator != 0:
                    correlation = numerator / denominator
                else:
                    correlation = 0
                
                # Determine strength of correlation
                abs_corr = abs(correlation)
                if abs_corr >= 0.7:
                    strength = "Strong"
                elif abs_corr >= 0.5:
                    strength = "Moderate"
                elif abs_corr >= 0.3:
                    strength = "Weak"
                else:
                    strength = "Negligible"
                
                correlations[factor] = {
                    'correlation': round(correlation, 2),
                    'strength': strength,
                    'sample_size': len(valid_points),
                    'direction': 'Positive' if correlation > 0 else 'Negative'
                }
    except Exception as e:
        print(f"Error calculating macro correlations: {str(e)}")
    
    return correlations

def generate_macro_insights(correlations: dict, macro_data_points: list) -> list:
    """
    Generate insights based on correlations between macro factors and market performance.
    
    Args:
        correlations: Dictionary of correlation results
        macro_data_points: List of dictionaries with macro data and price changes
        
    Returns:
        list: Insights about how macro environments affect similar events
    """
    insights = []
    
    try:
        # Check if we have meaningful correlations
        has_significant_correlation = any(
            c['strength'] in ['Moderate', 'Strong'] 
            for c in correlations.values()
        )
        
        if not has_significant_correlation:
            insights.append("No significant correlations found between macro factors and market performance.")
            return insights
        
        # Generate insights for each significant correlation
        for factor, data in correlations.items():
            if data['strength'] in ['Moderate', 'Strong']:
                factor_names = {
                    'cpi': 'inflation (CPI)',
                    'fed_rate': 'Federal Funds Rate',
                    'unemployment': 'unemployment rate',
                    'yield_curve': 'yield curve spread (10Y-2Y)'
                }
                
                direction = "higher" if data['correlation'] > 0 else "lower"
                factor_name = factor_names.get(factor, factor)
                
                insight = f"{data['strength']} {data['direction']} correlation ({data['correlation']}) between {factor_name} and market performance: "
                insight += f"{factor_name} tends to correlate with {direction} returns during similar events."
                
                insights.append(insight)
        
        # Add insights about current environment if possible
        if len(macro_data_points) >= 3:
            # Group events by macro regime
            high_inflation_events = [p for p in macro_data_points if p.get('cpi', 0) > 3.0]
            low_inflation_events = [p for p in macro_data_points if p.get('cpi', 0) <= 3.0 and p.get('cpi') is not None]
            
            high_rates_events = [p for p in macro_data_points if p.get('fed_rate', 0) > 3.0]
            low_rates_events = [p for p in macro_data_points if p.get('fed_rate', 0) <= 3.0 and p.get('fed_rate') is not None]
            
            # Calculate average performance in different regimes
            if len(high_inflation_events) >= 2 and len(low_inflation_events) >= 2:
                avg_high_inflation = sum(p['price_change'] for p in high_inflation_events) / len(high_inflation_events)
                avg_low_inflation = sum(p['price_change'] for p in low_inflation_events) / len(low_inflation_events)
                
                if abs(avg_high_inflation - avg_low_inflation) > 3.0:  # Only report if difference is significant
                    better_regime = "high inflation" if avg_high_inflation > avg_low_inflation else "low inflation"
                    insight = f"Similar events performed better during {better_regime} environments "
                    insight += f"({round(max(avg_high_inflation, avg_low_inflation), 1)}% vs {round(min(avg_high_inflation, avg_low_inflation), 1)}% average returns)."
                    insights.append(insight)
            
            if len(high_rates_events) >= 2 and len(low_rates_events) >= 2:
                avg_high_rates = sum(p['price_change'] for p in high_rates_events) / len(high_rates_events)
                avg_low_rates = sum(p['price_change'] for p in low_rates_events) / len(low_rates_events)
                
                if abs(avg_high_rates - avg_low_rates) > 3.0:  # Only report if difference is significant
                    better_regime = "high interest rate" if avg_high_rates > avg_low_rates else "low interest rate"
                    insight = f"Similar events performed better during {better_regime} environments "
                    insight += f"({round(max(avg_high_rates, avg_low_rates), 1)}% vs {round(min(avg_high_rates, avg_low_rates), 1)}% average returns)."
                    insights.append(insight)
            
            # Check for inverted yield curves
            inverted_events = [p for p in macro_data_points if p.get('yield_curve', 0) < 0]
            normal_events = [p for p in macro_data_points if p.get('yield_curve', 0) >= 0 and p.get('yield_curve') is not None]
            
            if len(inverted_events) >= 2 and len(normal_events) >= 2:
                avg_inverted = sum(p['price_change'] for p in inverted_events) / len(inverted_events)
                avg_normal = sum(p['price_change'] for p in normal_events) / len(normal_events)
                
                if abs(avg_inverted - avg_normal) > 3.0:  # Only report if difference is significant
                    better_regime = "inverted yield curve" if avg_inverted > avg_normal else "normal yield curve"
                    insight = f"Similar events performed better during {better_regime} environments "
                    insight += f"({round(max(avg_inverted, avg_normal), 1)}% vs {round(min(avg_inverted, avg_normal), 1)}% average returns)."
                    insights.append(insight)
    
    except Exception as e:
        print(f"Error generating macro insights: {str(e)}")
        insights.append(f"Error generating macro insights: {str(e)}")
    
    return insights

def call_openai_with_retry(model, messages, temperature=0.3, response_format=None, max_retries=MAX_RETRIES):
    """
    Call OpenAI API with retry mechanism for common errors.
    
    Args:
        model: OpenAI model to use
        messages: List of message dictionaries
        temperature: Temperature setting for generation
        response_format: Optional response format (e.g., JSON)
        max_retries: Maximum number of retry attempts
        
    Returns:
        OpenAI response object or None if failed
    """
    attempts = 0
    last_error = None
    
    while attempts < max_retries:
        try:
            # Prepare kwargs based on whether response_format is provided
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature
            }
            if response_format:
                kwargs["response_format"] = response_format
                
            # Check which API version we're using
            if hasattr(openai, 'ChatCompletion'):
                # Using older OpenAI library (v0.28.0)
                return openai.ChatCompletion.create(**kwargs)
            else:
                # Using newer OpenAI library
                return openai.chat.completions.create(**kwargs)
            
        except Exception as e:
            # Handle rate limiting
            if str(e).find('rate limit') >= 0:
                wait_time = min(2 ** attempts * RETRY_DELAY_SECONDS, 60)  # Exponential backoff
                print(ERROR_MESSAGES["openai_rate_limit"].format(wait_time))
                time.sleep(wait_time)
                last_error = e
            # Handle authentication errors
            elif str(e).find('authentication') >= 0 or str(e).find('API key') >= 0:
                print(ERROR_MESSAGES["openai_auth"])
                return None  # Auth errors won't be fixed by retrying
            # Handle connection errors
            elif str(e).find('connection') >= 0:
                attempts += 1
                print(ERROR_MESSAGES["openai_connection"].format(attempts, max_retries))
                time.sleep(RETRY_DELAY_SECONDS)
                last_error = "Connection error"
            # Handle other errors
            else:
                attempts += 1
                print(ERROR_MESSAGES["openai_general"].format(str(e)))
                time.sleep(RETRY_DELAY_SECONDS)
                last_error = e
            
        # Increment attempts for rate limit errors too
        attempts += 1
    
    # If we exhaust all retries
    print(f"Failed to get OpenAI response after {max_retries} attempts. Last error: {last_error}")
    return None

def display_formula(formula_name, formula_text, variables, result):
    """
    Display a formula with its actual values and result.
    
    Args:
        formula_name: Name of the formula
        formula_text: Generic text representation of the formula
        variables: Dictionary of variable names and their values
        result: The calculated result
    """
    print(f"\n📊 FORMULA: {formula_name}")
    print(f"EXPRESSION: {formula_text}")
    print("VALUES:")
    for var_name, var_value in variables.items():
        if isinstance(var_value, float):
            print(f"  {var_name} = {var_value:.4f}")
        else:
            print(f"  {var_name} = {var_value}")
    print(f"RESULT: {result}")
    print(f"CALCULATION DETAILS:")
    
    # Replace variables with their values in the formula
    calculation = formula_text
    for var_name, var_value in sorted(variables.items(), key=lambda x: len(x[0]), reverse=True):
        if isinstance(var_value, float):
            calculation = calculation.replace(var_name, f"{var_value:.4f}")
        else:
            calculation = calculation.replace(var_name, str(var_value))
    
    print(f"  {calculation} = {result}")

def extract_keywords(query):
    """
    Extract key search terms from a user query.
    
    Args:
        query: User's input query
        
    Returns:
        List of keywords for news filtering
    """
    # Common filler words to ignore
    stop_words = set([
        "a", "about", "an", "and", "are", "as", "at", "be", "by", "for", "from", 
        "has", "have", "how", "i", "in", "is", "it", "of", "on", "or", "that", 
        "the", "this", "to", "was", "what", "when", "where", "which", "who", "will", 
        "with", "would", "what's", "how's", "happened", "did", "affect", "impact"
    ])
    
    # Clean the query
    cleaned = query.lower()
    
    # Extract financial terms, entities, and important keywords
    # Look for financial instruments (stocks, bonds, etc.)
    financial_instruments = re.findall(r'(?:stocks?|bonds?|equit(?:y|ies)|crypto(?:currency)?s?|etfs?|options?|futures?|derivatives?)', cleaned)
    
    # Look for ticker symbols (uppercase 1-5 character sequences)
    tickers = re.findall(r'\b[A-Z]{1,5}\b', query)
    
    # Look for percentages and numbers with % signs
    percentages = re.findall(r'\d+(?:\.\d+)?%', cleaned)
    
    # Look for dollar amounts
    dollar_amounts = re.findall(r'\$\d+(?:,\d+)*(?:\.\d+)?(?:\s*(?:billion|million|trillion|b|m|t))?', cleaned)
    
    # Look for economic terms
    economic_terms = re.findall(r'(?:inflation|gdp|interest rate|fed(?:eral reserve)?|unemployment|cpi|ppi|yield curve|recession|tariff)', cleaned)
    
    # Look for market events
    event_terms = re.findall(r'(?:crash|correction|rally|bull|bear|surge|plunge|drop|rise|fell|bubble|merger|acquisition|ipo|split|dividend|earnings|report)', cleaned)
    
    # Look for time periods
    time_terms = re.findall(r'(?:today|yesterday|last week|last month|last year|recent|current|latest)', cleaned)
    
    # Split into words and filter stop words
    words = [word.strip('.,?!:;()[]{}"\'-') for word in cleaned.split()]
    filtered_words = [word for word in words if word not in stop_words and len(word) > 2]
    
    # Combine all extracted terms, removing duplicates
    all_terms = list(set(financial_instruments + tickers + economic_terms + event_terms))
    
    # If we found specific terms, use those; otherwise use filtered words
    if all_terms:
        # Add any percentages and dollar amounts
        all_terms.extend(percentages + dollar_amounts)
        # Add time terms for recency
        all_terms.extend(time_terms)
        return all_terms
    else:
        # If no specific financial terms found, use filtered general words
        return filtered_words

def calculate_news_relevance(headline, keywords, query):
    """
    Calculate how relevant a news headline is to the query.
    
    Args:
        headline: News headline dictionary
        keywords: List of extracted keywords
        query: Original user query
        
    Returns:
        Relevance score (0-100) and list of matched terms
    """
    relevance_score = 0
    matched_terms = []
    
    # Get the text content to search
    title = headline.get('title', '').lower()
    summary = headline.get('summary', '').lower()
    content = title + " " + summary
    
    # Check for exact query matches first (highest relevance)
    query_lower = query.lower()
    if query_lower in content:
        relevance_score += 50
        matched_terms.append(f"Exact query: '{query}'")
    
    # Check for keyword matches
    for keyword in keywords:
        keyword_lower = keyword.lower()
        if keyword_lower in content:
            # Add to matched terms
            matched_terms.append(keyword)
            
            # Calculate score based on where match was found and keyword importance
            if keyword_lower in title:
                # Keywords in title are more important
                relevance_score += 15
            else:
                # Keywords in summary
                relevance_score += 10
                
            # Give bonus for economic indicator and major event terms
            if keyword_lower in ['inflation', 'fed', 'interest rate', 'tariff', 'recession', 'unemployment']:
                relevance_score += 5
    
    # Cap the score at 100
    relevance_score = min(relevance_score, 100)
    
    return relevance_score, list(set(matched_terms))

def get_relevant_news(user_query, max_headlines=10, hours_lookback=24, relevance_threshold=25):
    """
    Get recent financial news relevant to the user's query.
    
    Args:
        user_query: User's input query
        max_headlines: Maximum number of headlines to return
        hours_lookback: Only consider headlines from the last X hours
        relevance_threshold: Minimum relevance score (0-100) to include a headline
        
    Returns:
        List of relevant headlines with source info and relevance data
    """
    try:
        print(f"Fetching and analyzing recent financial news (last {hours_lookback} hours)...")
        
        # Extract keywords from the query
        keywords = extract_keywords(user_query)
        print(f"Search keywords: {', '.join(keywords)}")
        
        # Get all headlines
        all_headlines = fetch_rss_headlines()
        if not all_headlines:
            print("⚠️ No headlines retrieved from RSS feeds")
            return []
            
        print(f"✓ Retrieved {len(all_headlines)} headlines from RSS feeds")
        
        # Filter for recent headlines
        cutoff_time = datetime.now() - timedelta(hours=hours_lookback)
        cutoff_str = cutoff_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        recent_headlines = [
            h for h in all_headlines 
            if h.get('published', '') >= cutoff_str
        ]
        
        print(f"✓ Found {len(recent_headlines)} headlines from the last {hours_lookback} hours")
        
        # Calculate relevance for each headline
        relevant_headlines = []
        for headline in recent_headlines:
            relevance_score, matched_terms = calculate_news_relevance(headline, keywords, user_query)
            
            # Add relevance data to the headline
            headline['relevance_score'] = relevance_score
            headline['matched_terms'] = matched_terms
            
            # Only include headlines above the relevance threshold
            if relevance_score >= relevance_threshold and matched_terms:
                relevant_headlines.append(headline)
        
        # Sort by relevance score (highest first)
        relevant_headlines.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        
        # Take the top headlines
        top_headlines = relevant_headlines[:max_headlines]
        
        print(f"✓ Found {len(top_headlines)} relevant headlines matching query keywords")
        return top_headlines
        
    except Exception as e:
        print(f"⚠️ Error fetching relevant news: {str(e)}")
        return []

def enhance_query_with_context(user_query: str):
    """
    Enhance the user query with context and keywords to improve LLM understanding.
    
    Args:
        user_query: User's input query
        
    Returns:
        Enhanced query with context prompting
    """
    # For complex queries with multiple questions, break it down
    parts = re.split(r'[.?!]\s+', user_query)
    parts = [p.strip() + '?' if not p.endswith('?') and len(p) > 10 else p for p in parts if p.strip()]
    
    # Identify key themes in the query
    themes = []
    if any(term in user_query.lower() for term in ['risk on', 'risk off', 'risk-on', 'risk-off']):
        themes.append('risk sentiment')
    if any(term in user_query.lower() for term in ['latest', 'recent', 'new', 'current']):
        themes.append('recent developments')
    if any(term in user_query.lower() for term in ['impact', 'affect', 'effect', 'implications']):
        themes.append('market impact')
    if any(term in user_query.lower() for term in ['trade', 'position', 'investment', 'strategy', 'recommendation']):
        themes.append('trade recommendations')
    
    # Create enhanced query with additional context
    enhanced_query = user_query
    
    if themes:
        theme_guidance = f"\nPlease analyze this query in terms of: {', '.join(themes)}."
        enhanced_query += theme_guidance
    
    if len(parts) > 1:
        question_breakdown = "\nThis query contains multiple questions:\n"
        for i, part in enumerate(parts, 1):
            if part.strip() and len(part) > 5:
                question_breakdown += f"{i}. {part.strip()}\n"
        enhanced_query += question_breakdown + "Please address each question component in your response."
    
    return enhanced_query

def visualize_llm_input_formula(data_sources, full_context=None):
    """
    Visualize the formula of inputs that went into the LLM query.
    
    Args:
        data_sources: Dictionary of all data sources used
        full_context: The full context sent to the LLM
    """
    print("\n🧮 LLM INPUT FORMULA")
    print("===========================================================")
    print("FORMULA: Final_Output = LLM(User_Query + Enhanced_Context + News_Articles + Macro_Data)")
    
    # Summarize values used
    print("\nVALUES FED INTO THE FORMULA:")
    print("1. User_Query:")
    print(f"   \"{data_sources['user_query']}\"")
    
    # Show enhancement if applied
    if 'enhanced_query' in data_sources and data_sources['enhanced_query'] != data_sources['user_query']:
        print("\n2. Enhanced_Context:")
        additions = data_sources['enhanced_query'].replace(data_sources['user_query'], '').strip()
        print(f"   \"{additions}\"")
    
    # Show news articles
    print("\n3. News_Articles:")
    if data_sources["news_sources"]:
        for i, news in enumerate(data_sources["news_sources"][:5], 1):
            relevance = news.get('relevance', 'N/A')
            relevance_str = f"{relevance}%" if isinstance(relevance, (int, float)) else relevance
            print(f"   {i}. [{news['source']}] {news['headline']} (Relevance: {relevance_str})")
        if len(data_sources["news_sources"]) > 5:
            print(f"   ... and {len(data_sources['news_sources']) - 5} more articles")
    else:
        print("   None")
    
    # Show macro indicators
    print("\n4. Macro_Data:")
    if "macro_data" in data_sources and data_sources["macro_data"]:
        for key, value in data_sources["macro_data"].items():
            if key != "source":
                print(f"   - {key.replace('_', ' ').title()}: {value}")
    else:
        print("   None")
    
    # Show historical data if used
    if "historical_analysis" in data_sources and data_sources["historical_analysis"]:
        print("\n5. Historical_Analysis:")
        hist = data_sources["historical_analysis"]
        print(f"   - Event Date: {hist.get('event_date', 'N/A')}")
        print(f"   - Ticker: {hist.get('ticker', 'N/A')}")
        print(f"   - Price Change: {hist.get('price_change_pct', 'N/A')}%")
    
    # Show prompt statistics
    if full_context:
        tokens_estimate = len(full_context.split()) * 1.33  # Rough estimate
        print(f"\nTotal estimated tokens in prompt: ~{int(tokens_estimate)}")
    
    print("\nOUTPUT TRANSFORMATION:")
    print("1. Raw LLM Output → Parsed into sections")
    print("2. Sections enriched with data visualization")
    print("3. Final response formatted for user display")
    
    print("\nFORMULA WEIGHT DISTRIBUTION:")
    # Calculate approximate weights
    total_weight = 100
    user_query_weight = 25
    news_weight = 35 if data_sources["news_sources"] else 0
    macro_weight = 20 if "macro_data" in data_sources and data_sources["macro_data"] else 0
    historical_weight = 20 if "historical_analysis" in data_sources and data_sources["historical_analysis"] else 0
    
    # Redistribute weights if some data is missing
    remaining = total_weight - (user_query_weight + news_weight + macro_weight + historical_weight)
    if remaining > 0:
        # Distribute remaining weight proportionally
        if user_query_weight > 0:
            user_query_weight += remaining * (user_query_weight / (user_query_weight + news_weight + macro_weight + historical_weight))
        if news_weight > 0:
            news_weight += remaining * (news_weight / (user_query_weight + news_weight + macro_weight + historical_weight))
        if macro_weight > 0:
            macro_weight += remaining * (macro_weight / (user_query_weight + news_weight + macro_weight + historical_weight))
        if historical_weight > 0:
            historical_weight += remaining * (historical_weight / (user_query_weight + news_weight + macro_weight + historical_weight))
    
    print(f"User Query:         {user_query_weight:.1f}%")
    print(f"News Articles:      {news_weight:.1f}%")
    print(f"Macro Environment:  {macro_weight:.1f}%")
    print(f"Historical Data:    {historical_weight:.1f}%")

def process_query(user_input: str, session_id=None, is_follow_up=None, model=None):
    """
    Process a query and maintain conversation context.
    
    Args:
        user_input: The user's query text
        session_id: Optional ID for continuing a conversation
        is_follow_up: Optional flag to force treating as follow-up
        model: Optional model to use for this query (defaults to DEFAULT_MODEL)
        
    Returns:
        tuple: (response, session_id) - response is the analysis result,
               session_id can be used for follow-up questions
    """
    # Use the provided model or fall back to DEFAULT_MODEL
    model_to_use = model or DEFAULT_MODEL
    
    try:
        # Clean up old sessions periodically
        clean_old_sessions()
        
        # Get or create session
        session = get_session(session_id)
        
        # Auto-detect if this is a follow-up question if not specified
        if is_follow_up is None:
            is_follow_up = session.is_follow_up_question(user_input)
        
        # Add query to history
        session.add_query(user_input, is_follow_up)
        
        print("\n🔄 DATA FLOW: INITIALIZING QUERY PROCESSING")
        print("------------------------------------------------------------")
        print("📌 SYSTEM VERSION INFO:")
        print(f"- OpenAI API Key: {'Available' if OPENAI_API_KEY else 'Not Available'}")
        print(f"- FRED API Key: {'Available' if FRED_API_KEY else 'Not Available'}")
        print(f"- Default Model: {model_to_use}")
        print(f"- Max Retries: {MAX_RETRIES}")
        print(f"- Session ID: {session.session_id}")
        print(f"- Is Follow-up Question: {is_follow_up}")
        
        # Check if saving is enabled
        save_enabled = os.environ.get("SAVE_ANALYSIS", "1") == "1"
        export_file = os.environ.get("EXPORT_ANALYSIS", "")
        
        # For initial queries (non-follow-ups), validate if market-related
        if not is_follow_up and not is_valid_market_query(user_input):
            print("\nInvalid query detected. Please ask a specific question about market events.")
            print("Examples:")
            print("  - What happened when Bitcoin ETF was approved?")
            print("  - How would inflation at 4% affect tech stocks?")
            print("  - What's the impact of Fed raising rates by 50 basis points?")
            return "Please ask a specific question about market events or financial topics.", session.session_id
            
        # Enhance the query
        enhanced_query = enhance_query_with_context(user_input)
        
        # Keep track of all data sources for this query
        data_sources = {
            "user_query": user_input,
            "enhanced_query": enhanced_query,
            "news_sources": [],
            "market_data": [],
            "macro_data": [],
            "historical_events": []
        }
        
        # Check if we're in historical context mode from previous interactions
        historical_mode = False
        historical_date = None
        
        # For follow-up questions, check if previous analysis was about a historical event
        if is_follow_up and session.data_sources.get("historical_analysis"):
            hist_analysis = session.data_sources.get("historical_analysis", {})
            if hist_analysis.get("success") and hist_analysis.get("event_date"):
                historical_mode = True
                historical_date = hist_analysis.get("event_date")
                print(f"\n📅 DETECTED HISTORICAL FOLLOW-UP CONTEXT: {historical_date}")
        
        # For follow-up questions, include context from previous interactions
        if is_follow_up and session.query_history and len(session.query_history) > 1:
            context_summary = session.generate_context_summary()
            print("\n📝 ADDING PREVIOUS CONVERSATION CONTEXT")
            enhanced_query = enhanced_query + "\n\n" + context_summary
        
        # Fetch relevant financial news based on the query
        print("\n🔄 DATA FLOW: FETCHING RELEVANT FINANCIAL NEWS")
        print("------------------------------------------------------------")
        print("FUNCTION: get_relevant_news()")
        print("SOURCE: rss_ingestor.py + custom relevance filtering")
        print("RSS FEEDS: Yahoo Finance, CNBC, Reuters, Financial Times, Bloomberg")
        print(f"QUERY: '{user_input}'")
        
        # Extract keywords from the query
        query_keywords = extract_keywords(user_input)
        print(f"KEYWORDS: {', '.join(query_keywords)}")
        
        # Skip current news if we're in historical mode for a follow-up question
        if historical_mode:
            print(f"\n📌 HISTORICAL CONTEXT MODE: Skipping current news for historical analysis from {historical_date}")
            relevant_headlines = []
        else:
            # Get news relevant to the query
            relevant_headlines = get_relevant_news(user_input, max_headlines=7, hours_lookback=48, relevance_threshold=15)
            
            if relevant_headlines:
                print("\n📰 RELEVANT FINANCIAL NEWS:")
                for i, headline in enumerate(relevant_headlines, 1):
                    published = headline.get('published', '').replace('T', ' ').replace('Z', '')
                    relevance = headline.get('relevance_score', 0)
                    matched = ', '.join(headline.get('matched_terms', []))
                    
                    # Add to data sources
                    data_sources["news_sources"].append({
                        "headline": headline['title'],
                        "source": headline['source'],
                        "date": published,
                        "relevance": relevance,
                        "matched_terms": headline.get('matched_terms', [])
                    })
                    
                    print(f"{i}. [{headline['source']}] {headline['title']} ({published})")
                    print(f"   RELEVANCE: {relevance}% - Matched: {matched}")
            else:
                print("\n⚠️ No recent news stories found relevant to your query")
                print("   Fetching general financial news instead...")
                
                # Fall back to recent general news
                all_headlines = fetch_rss_headlines()
                # Filter for recent headlines
                cutoff_time = datetime.now() - timedelta(hours=48)
                cutoff_str = cutoff_time.strftime("%Y-%m-%dT%H:%M:%SZ")
                recent_headlines = [h for h in all_headlines if h.get('published', '') >= cutoff_str]
                recent_headlines.sort(key=lambda x: x.get('published', ''), reverse=True)
                relevant_headlines = recent_headlines[:5]  # Get the 5 most recent headlines
                
                if relevant_headlines:
                    print("\n📰 RECENT GENERAL FINANCIAL NEWS (no specific matches):")
                    for i, headline in enumerate(relevant_headlines, 1):
                        published = headline.get('published', '').replace('T', ' ').replace('Z', '')
                        print(f"{i}. [{headline['source']}] {headline['title']} ({published})")
                        
                        # Add to data sources
                        data_sources["news_sources"].append({
                            "headline": headline['title'],
                            "source": headline['source'],
                            "date": published,
                            "relevance": "General news"
                        })
        
        # Store the news sources in the session
        if data_sources["news_sources"]:
            session.add_data_source("news_sources", data_sources["news_sources"])
        
        # Prepare context from relevant news
        news_context = ""
        if relevant_headlines:
            news_context = "RECENT RELEVANT FINANCIAL NEWS:\n"
            for headline in relevant_headlines:
                published = headline.get('published', '').replace('T', ' ').replace('Z', '')
                matched_terms = ', '.join(headline.get('matched_terms', []))
                
                news_context += f"- [{headline['source']}] {headline['title']} ({published})\n"
                if matched_terms:
                    news_context += f"  Relevance: Matches terms [{matched_terms}]\n"
                    
                if 'summary' in headline:
                    # Clean and truncate summary
                    summary = html.unescape(headline['summary'])
                    summary = re.sub(r'<[^>]+>', '', summary)  # Remove HTML tags
                    if len(summary) > 200:
                        summary = summary[:197] + "..."
                    news_context += f"  Summary: {summary}\n"
        
        # Get current macro data for context only if not in historical mode
        if historical_mode:
            print(f"\n📌 HISTORICAL CONTEXT MODE: Using historical macro data from {historical_date} instead of current data")
            macro_context = ""
            if historical_date:
                try:
                    historical_macro = get_historical_macro_data(historical_date)
                    if historical_macro:
                        macro_context = f"\nMACRO ENVIRONMENT (AS OF {historical_date}):\n"
                        macro_context += f"- Inflation (CPI): {historical_macro.get('CoreCPI', 'N/A')}%\n"
                        macro_context += f"- Fed Funds Rate: {historical_macro.get('FedFundsRate', 'N/A')}%\n"
                        macro_context += f"- Unemployment: {historical_macro.get('Unemployment', 'N/A')}%\n"
                        macro_context += f"- 10Y Treasury: {historical_macro.get('TenYearYield', 'N/A')}%\n"
                        
                        # Add to data sources
                        data_sources["macro_data"] = historical_macro
                        
                        # Store macro data in the session
                        session.add_data_source("macro_data", data_sources["macro_data"])
                except Exception as e:
                    print(f"⚠️ Error fetching historical macro data: {str(e)}")
                    macro_context = ""
        else:
            try:
                macro_snapshot = get_macro_snapshot()
                if macro_snapshot:
                    macro_context = "\nCURRENT MACRO ENVIRONMENT:\n"
                    macro_context += f"- Inflation (CPI): {macro_snapshot.get('CPI_YoY', 'N/A')}%\n"
                    macro_context += f"- Fed Funds Rate: {macro_snapshot.get('FedFundsRate', 'N/A')}%\n"
                    macro_context += f"- Unemployment: {macro_snapshot.get('Unemployment', 'N/A')}%\n"
                    macro_context += f"- 10Y Treasury: {macro_snapshot.get('TenYearYield', 'N/A')}%\n"
                    
                    # Add to data sources
                    data_sources["macro_data"] = {
                        "inflation": macro_snapshot.get('CPI_YoY', 'N/A'),
                        "fed_rate": macro_snapshot.get('FedFundsRate', 'N/A'),
                        "unemployment": macro_snapshot.get('Unemployment', 'N/A'),
                        "ten_year_yield": macro_snapshot.get('TenYearYield', 'N/A'),
                        "source": "FRED Economic Data"
                    }
                    
                    # Store macro data in the session
                    session.add_data_source("macro_data", data_sources["macro_data"])
            except Exception as e:
                print(f"⚠️ Error fetching macro data: {str(e)}")
                macro_context = ""
        
        print("\n🔄 DATA FLOW: SENDING QUERY TO LLM")
        print("------------------------------------------------------------")
        print(f"📥 INPUT QUERY: '{user_input}'")
        if enhanced_query != user_input:
            print(f"📝 ENHANCED QUERY: '{enhanced_query}'")
        print(f"🤖 LLM MODEL: {model_to_use}")
        
        # Build the full context for the LLM
        full_context = enhanced_query
        if news_context:
            full_context += f"\n\n{news_context}"
            print("\n📰 NEWS INTEGRATED INTO PROMPT")
        if macro_context:
            full_context += f"\n{macro_context}"
            print("\n📊 MACRO DATA INTEGRATED INTO PROMPT")
        
        # Store the full context for final formula visualization
        data_sources["full_context"] = full_context
        session.last_full_context = full_context
        
        # Craft a better system message for complex queries
        system_message = """You are a sophisticated financial analyst with expertise in market events, economic trends, and trading strategies. 
When analyzing user queries:
1) First identify the key market events or trends mentioned
2) Analyze the current news and macro environment that's relevant
3) Provide a clear market analysis with directional outlook
4) End with a specific, actionable trade idea with rationale

Structure your response with these clearly labeled sections:
1. MARKET ANALYSIS: Your assessment of the current situation and trends
2. DIRECTIONAL OUTLOOK: Clear stance on market direction (bullish/bearish/neutral) with supporting evidence
3. TRADE RECOMMENDATION: Specific actionable trade idea with ticker, direction, timeframe, and risk level
"""

        # For historical analysis context, modify the system message
        if historical_mode:
            system_message = f"""You are a sophisticated financial analyst with expertise in market events, economic trends, and trading strategies.
You are discussing a historical market event from {historical_date} and should only reference information available at that time.

When responding:
1) Focus on explaining what happened during this historical period
2) Do NOT use current market data or news in your analysis
3) Provide historical context and factual information about the event
4) Only if explicitly requested, suggest what trade strategies would have worked at that time

IMPORTANT: Do NOT make current trade recommendations or reference current market conditions.
Structure your response in a conversational format that focuses on the historical context.
"""

        # For follow-up questions about historical events, modify the system message
        if is_follow_up and historical_mode:
            system_message = f"""You are a sophisticated financial analyst with expertise in market events, economic trends, and trading strategies.
This is a follow-up question about a historical market event from {historical_date}.

When responding:
1) Acknowledge the previous conversation context about this historical event
2) Address the specific follow-up question while maintaining historical accuracy
3) Only reference information and market conditions from that time period
4) Do NOT reference current market data or make current trade recommendations

IMPORTANT: Maintain the historical context and only discuss what was known at that time.
Structure your response in a conversational format that addresses the specific follow-up question.
"""
        # For regular follow-up questions (non-historical), use this system message
        elif is_follow_up:
            system_message = """You are a sophisticated financial analyst with expertise in market events, economic trends, and trading strategies.
This is a follow-up question in an ongoing conversation about financial markets and investments.
When responding:
1) Acknowledge the previous conversation context provided
2) Address the specific follow-up question with the context in mind 
3) Provide a clear, updated market analysis that builds on previous insights
4) End with a specific, actionable trade idea that considers both the new question and previous context

Structure your response with these clearly labeled sections:
1. MARKET ANALYSIS: Your updated assessment considering both previous context and new information
2. DIRECTIONAL OUTLOOK: Clear stance on market direction with supporting evidence
3. TRADE RECOMMENDATION: Specific actionable trade idea with ticker, direction, timeframe, and risk level
"""
        
        # Store the system message
        session.last_system_message = system_message
        
        # Send query to LLM
        print("📋 EXACT PROMPT TO LLM:")
        print(f"System: {system_message}")
        print(f"User: {full_context}")
        
        # Use retry mechanism for OpenAI API call
        response = call_openai_with_retry(
            model=model_to_use,
            messages=[
                {
                    "role": "system",
                    "content": system_message
                },
                {
                    "role": "user",
                    "content": full_context
                }
            ],
            temperature=0.2
        )
        
        # Handle case where OpenAI API call completely failed
        if not response:
            print("\n⚠️ Could not process query with LLM. Using simplified processing.")
            parsed_event = "Market event analysis (simplified due to API error)."
            llm_output = "Error receiving response from language model."
        else:
            # Extract and sanitize the response content
            parsed_event = sanitize_text(response.choices[0].message.content)
            llm_output = parsed_event
            print("\n📤 LLM OUTPUT:")
            print("SOURCE: OpenAI API")
            print("CONTENT:")
            print(parsed_event)
        
        # Add to data sources
        data_sources["llm_output"] = llm_output
        
        # Extract date if available
        event_date, ticker_symbol, event_description = extract_date_from_query(user_input, parsed_event)
        
        # If we're analyzing a historical event, do that analysis now
        has_historical_data = False
        if event_date:
            print(f"\n📅 Detected Historical Event: {event_date}")
            print(f"📊 Analyzing market impact for ticker: {ticker_symbol}")
            
            historical_analysis = analyze_historical_event(event_date, ticker_symbol)
            has_historical_data = historical_analysis.get("success", False)
            
            if has_historical_data:
                # Add historical analysis to data sources
                data_sources["historical_analysis"] = historical_analysis
                
                # Store historical analysis in the session
                session.add_data_source("historical_analysis", historical_analysis)
                print(f"\n✅ Historical analysis completed for {ticker_symbol} on {event_date}")
        
        # Extract and display the market analysis, outlook and trade recommendation
        sections = {
            "MARKET ANALYSIS": "",
            "DIRECTIONAL OUTLOOK": "",
            "TRADE RECOMMENDATION": ""
        }
        
        # For historical mode, use a simplified format without sections
        if historical_mode:
            sections = {"HISTORICAL CONTEXT": llm_output}
        else:
            # Try to identify the sections in the LLM output
            current_section = None
            for line in llm_output.split('\n'):
                # Check if the line indicates a section header
                for section in sections:
                    if section in line.upper() or line.strip().upper() == section:
                        current_section = section
                        continue
                
                # Add the line to the current section if we're in one
                if current_section and line.strip() and not any(s in line.upper() for s in sections):
                    sections[current_section] += line + "\n"
            
            # If we couldn't find explicit sections, try to infer them
            if not any(sections.values()):
                # Split the text into paragraphs
                paragraphs = [p for p in llm_output.split('\n\n') if p.strip()]
                
                if len(paragraphs) >= 3:
                    sections["MARKET ANALYSIS"] = paragraphs[0]
                    sections["DIRECTIONAL OUTLOOK"] = paragraphs[1]
                    sections["TRADE RECOMMENDATION"] = paragraphs[-1]
                elif len(paragraphs) == 2:
                    sections["MARKET ANALYSIS"] = paragraphs[0]
                    sections["TRADE RECOMMENDATION"] = paragraphs[1]
                else:
                    # Just use the whole thing as market analysis
                    sections["MARKET ANALYSIS"] = llm_output
        
        # Store response in the conversation history
        session.add_llm_response(llm_output, sections)
        
        # Display the flow summary
        print("\n📊 ANALYSIS FLOW SUMMARY")
        print("===========================================================")
        print("INPUT ROUTING & DATA FLOW:")
        print(f"1. User Query: '{user_input}'")
        if enhanced_query != user_input:
            print(f"   → Enhanced to: '{enhanced_query}'")
        
        print("\n2. News Sources Integrated:")
        if data_sources["news_sources"]:
            for i, news in enumerate(data_sources["news_sources"][:3], 1):
                print(f"   {i}. [{news['source']}] {news['headline']}")
            if len(data_sources["news_sources"]) > 3:
                print(f"   ... and {len(data_sources['news_sources']) - 3} more headlines")
        else:
            print("   No relevant news found")
            
        print("\n3. Macro Environment Data:")
        if "macro_data" in data_sources and data_sources["macro_data"]:
            for key, value in data_sources["macro_data"].items():
                if key != "source":
                    print(f"   - {key.replace('_', ' ').title()}: {value}")
        else:
            print("   No macro data integrated")
            
        # If we did historical analysis, include it
        if "historical_analysis" in data_sources and data_sources["historical_analysis"].get("success", False):
            hist = data_sources["historical_analysis"] 
            print(f"\n4. Historical Event Analysis:")
            print(f"   - Event Date: {hist['event_date']}")
            print(f"   - Ticker: {hist['ticker']}")
            print(f"   - Price Change: {hist['price_change_pct']}%")
        
        # Include conversation context information for follow-up questions
        if is_follow_up:
            print("\n5. Conversation Context:")
            print(f"   - Session ID: {session.session_id}")
            print(f"   - Previous Queries: {len(session.query_history) - 1}")
            print(f"   - Data Points Carried Forward: {sum(1 for v in session.data_sources.values() if v)}")
            
        # Display the final response
        print("\n🔍 RESPONSE TO USER QUERY")
        print("===========================================================")
        
        # For historical mode responses, display in a conversational format
        if historical_mode:
            if "HISTORICAL CONTEXT" in sections:
                print("\nHISTORICAL ANALYSIS:")
                print(sections["HISTORICAL CONTEXT"].strip())
        else:
            if sections["MARKET ANALYSIS"]:
                print("\nMARKET ANALYSIS:")
                print(sections["MARKET ANALYSIS"].strip())
                
            if sections["DIRECTIONAL OUTLOOK"]:
                print("\nDIRECTIONAL OUTLOOK:")
                print(sections["DIRECTIONAL OUTLOOK"].strip())
                
            if sections["TRADE RECOMMENDATION"]:
                print("\n💼 TRADE SUGGESTION:")
                print(sections["TRADE RECOMMENDATION"].strip())
            else:
                print("\n💼 TRADE SUGGESTION:")
                print("No specific trade recommendation was generated. Consider gathering more specific market data.")
        
        # Visualize the input formula showing what went into the LLM
        visualize_llm_input_formula(data_sources, full_context)
        
        # Prepare the response for the user
        # For the command-line interface, we'll return the full formatted output
        # For a potential future Streamlit interface, this will be the content displayed to the user
        response = llm_output
        
        print("\n🔄 DATA FLOW: ANALYSIS COMPLETE")
        print("------------------------------------------------------------")
        print(f"📌 SESSION ID: {session.session_id} (use for follow-up questions)")
        
        # Return both the response and the session_id for continuity
        return response, session.session_id
        
    except Exception as e:
        print(f"\n⚠️ Critical error: {str(e)}")
        print("   Unable to process your query. Please check your input and try again.")
        print("   Error details: " + str(e).__class__.__name__ + ": " + str(e))
        
        # Return error message and None for session_id
        return f"Error: {str(e)}", None

def generate_enhanced_trade(user_input: str, classification: dict, macro_snapshot: dict, event_tags: dict, historical_data: str = None) -> dict:
    """
    Generate an enhanced trade recommendation with risk assessment and confidence rating.
    
    Args:
        user_input: User's query
        classification: Event classification
        macro_snapshot: Macroeconomic data
        event_tags: Event tags
        historical_data: Optional historical data as string
    
    Returns:
        dict: Trade recommendation
    """
    # Set up a prompt for generating a quality trade recommendation
    base_prompt = f"""
    Based on the following information, generate a high-quality options trade recommendation:
    
    USER QUERY: "{user_input}"
    
    EVENT CLASSIFICATION:
    - Type: {classification.get('event_type', 'Unknown')}
    - Sentiment: {classification.get('sentiment', 'Unknown')}
    - Sector: {classification.get('sector', 'Unknown')}
    
    MACRO ENVIRONMENT:
    - CPI: {macro_snapshot.get('CPI_YoY', 'Unknown')}%
    - Fed Funds Rate: {macro_snapshot.get('FedFundsRate', 'Unknown')}%
    - 10Y-2Y Spread: {round(macro_snapshot.get('TenYearYield', 0) - macro_snapshot.get('TwoYearYield', 0), 2)}%
    - Unemployment: {macro_snapshot.get('Unemployment', 'Unknown')}%
    
    EVENT CONTEXT:
    - During Fed Week: {event_tags.get('is_fed_week', False)}
    - During CPI Week: {event_tags.get('is_cpi_week', False)}
    - Earnings Season: {event_tags.get('is_earnings_season', False)}
    - Repeat Event: {event_tags.get('is_repeat_event', False)}
    """
    
    # Add historical data if available
    if historical_data:
        base_prompt += f"\n{historical_data}\n"
    
    # Add required JSON fields
    base_prompt += """
    You must return a complete JSON object with the following fields:
    - ticker: Symbol to trade (like "GBTC", "SPY", etc.)
    - trade_type: "option" (preferred) or "stock"
    - option_type: "CALL" or "PUT"
    - strike: Strike price (relative to current price if exact unknown)
    - expiration: Time period like "short-term", "medium-term", or "long-term"
    - risk_level: Number from 1-10 where 10 is highest risk
    - confidence: Number from 1-100 representing confidence percentage
    - market_environment: "risk-on" or "risk-off"
    - risk_reward: Expected risk/reward ratio like "1:3" or "1:5"
    - rationale: Detailed explanation of the trade rationale
    
    Return your full recommendation as JSON.
    """
    
    try:
        # Use improved OpenAI API call with retries
        response = call_openai_with_retry(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert options trading advisor who provides precise, actionable trade recommendations with risk assessment."},
                {"role": "user", "content": base_prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        # Handle case where API call completely failed
        if not response:
            raise Exception("Failed to get response from OpenAI API after multiple attempts")
        
        # Get the JSON response and parse it
        trade_json = response.choices[0].message.content
        
        try:
            trade_recommendation = json.loads(trade_json)
        except json.JSONDecodeError as e:
            print(f"⚠️ Error decoding JSON response: {e}")
            print("   Response content: " + trade_json[:100] + "..." if len(trade_json) > 100 else trade_json)
            raise Exception("Invalid JSON response from OpenAI API")
        
        # Create default values for any missing fields
        defaults = {
            "ticker": "SPY",
            "trade_type": "option",
            "option_type": "CALL" if classification.get("sentiment") == "Bullish" else "PUT",
            "strike": "ATM",
            "expiration": "medium-term (30-45 days)",
            "risk_level": 5,
            "confidence": 65,
            "market_environment": "neutral",
            "risk_reward": "1:2",
            "rationale": "Based on the current market conditions and event analysis."
        }
        
        # Fill in any missing fields with defaults
        for key, default_value in defaults.items():
            if key not in trade_recommendation or trade_recommendation[key] is None:
                trade_recommendation[key] = default_value
                
        return trade_recommendation
    
    except Exception as e:
        print(f"⚠️ Error generating enhanced trade: {str(e)}")
        # Return default recommendation in case of error
        return {
            "ticker": classification.get("sector", "SPY"),
            "trade_type": "option",
            "option_type": "CALL" if classification.get("sentiment", "") == "Bullish" else "PUT",
            "strike": "ATM",
            "expiration": "medium-term (30-45 days)",
            "risk_level": 5,
            "confidence": 50,
            "market_environment": "neutral",
            "risk_reward": "1:2",
            "rationale": "Default recommendation due to error in enhanced trade generation: " + str(e)
        }

def continuous_interactive_mode(model=DEFAULT_MODEL):
    """Run in continuous interactive mode until user explicitly exits."""
    print("\nWelcome to Market Event Analysis - Interactive Mode")
    print("Type 'exit' or 'quit' to end the conversation")
    print("Type 'reset' to start a new conversation session\n")
    
    # Create initial session
    session_id = create_new_session().session_id
    
    while True:
        try:
            # Get user input
            query = input("\nEnter your query: ").strip()
            
            # Check exit commands
            if query.lower() in ['exit', 'quit']:
                print("Conversation ended.")
                break
                
            # Check reset command
            if query.lower() == 'reset':
                session_id = create_new_session().session_id
                print("Conversation reset. New session started.")
                continue
                
            # Skip empty queries
            if not query:
                continue
                
            # Process the query within the current session
            response, new_session_id = process_query(query, session_id, model=model)
            
            # Update session ID if needed
            if new_session_id:
                session_id = new_session_id
                
        except KeyboardInterrupt:
            print("\nConversation ended.")
            break
        except Exception as e:
            print(f"Error processing query: {e}")
    
    return 0

def main():
    """Main function to process queries and handle conversations."""
    
    # Setup argument parser
    parser = argparse.ArgumentParser(description="Query about market events and get analysis with trade recommendations")
    parser.add_argument("query", nargs="*", help="Market event query (if not provided, interactive mode will start)")
    parser.add_argument("--session", metavar="SESSION_ID", help="Session ID for follow-up questions")
    parser.add_argument("--follow-up", action="store_true", help="Force treating as a follow-up question")
    parser.add_argument("--no-save", action="store_true", help="Don't save analysis results")
    parser.add_argument("--export", metavar="FILE", help="Export analysis results to specified file")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"OpenAI model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--days", type=int, default=30, help="Number of days to analyze (default: 30)")
    parser.add_argument("--dummy", action="store_true", help="Use dummy mode (no API calls)")
    parser.add_argument("--interactive", action="store_true", help="Start in interactive mode")
    args = parser.parse_args()
    
    # Update the model to use based on args
    model_to_use = args.model
    
    # Set environment variables based on args
    if args.no_save:
        os.environ["SAVE_ANALYSIS"] = "0"
    if args.export:
        os.environ["EXPORT_ANALYSIS"] = args.export
    
    # Start continuous interactive mode if no query is provided or interactive flag is set
    if not args.query or args.interactive:
        return continuous_interactive_mode(model_to_use)
        
    # Standard single-query mode
    query = " ".join(args.query)
    session_id = args.session if args.session else None
    
    # Process the query
    response, new_session_id = process_query(query, session_id, args.follow_up, model_to_use)
    
    # For the CLI, we've already printed the response, but we'll show the session ID
    # for follow-up questions
    if new_session_id:
        print(f"\nSession ID: {new_session_id}")
        print("To ask a follow-up question, use: python llm_event_query.py --session " + new_session_id + " 'your follow-up question'")
        print("Or simply run without arguments for interactive mode: python llm_event_query.py")
    
    return 0

def create_new_session():
    """Create a new conversation session."""
    session = ConversationContext()
    CONVERSATION_SESSIONS[session.session_id] = session
    return session

def get_session(session_id):
    """Get an existing session or create a new one."""
    if session_id and session_id in CONVERSATION_SESSIONS:
        return CONVERSATION_SESSIONS[session_id]
    return create_new_session()

def clean_old_sessions(max_age_hours=24):
    """Clean up old conversation sessions."""
    current_time = datetime.now()
    expired_sessions = []
    
    for session_id, session in CONVERSATION_SESSIONS.items():
        age = (current_time - session.creation_time).total_seconds() / 3600
        if age > max_age_hours:
            expired_sessions.append(session_id)
    
    for session_id in expired_sessions:
        del CONVERSATION_SESSIONS[session_id]
    
    return len(expired_sessions)

# Add this new class to manage conversation context
class ConversationContext:
    """
    Manages the context for a conversation session, including query history and analysis results.
    """
    def __init__(self, session_id=None):
        self.session_id = session_id or str(uuid.uuid4())
        self.query_history = []
        self.data_sources = {
            "news_sources": [],
            "market_data": [],
            "macro_data": {},
            "historical_analysis": {},
            "similar_events": []
        }
        self.llm_responses = []
        self.last_enhanced_query = ""
        self.last_full_context = ""
        self.last_system_message = ""
        self.creation_time = datetime.now()
        
    def add_query(self, query, is_follow_up=False):
        """Add a user query to the history."""
        self.query_history.append({
            "text": query,
            "timestamp": datetime.now(),
            "is_follow_up": is_follow_up
        })
        
    def add_llm_response(self, response_text, sections=None):
        """Add an LLM response to the history."""
        response_data = {
            "text": response_text,
            "timestamp": datetime.now(),
            "sections": sections or {}
        }
        self.llm_responses.append(response_data)
        
    def add_data_source(self, source_type, data):
        """Add or update a data source."""
        if source_type == "news_sources" and isinstance(data, list):
            # For news sources, append to the list
            self.data_sources["news_sources"].extend(data)
        elif source_type == "historical_analysis" and data.get("success", False):
            # For historical analysis, store the whole thing
            self.data_sources["historical_analysis"] = data
        elif source_type == "similar_events" and isinstance(data, list):
            # For similar events, store the list
            self.data_sources["similar_events"] = data
        elif source_type == "macro_data" and isinstance(data, dict):
            # For macro data, update the dict
            self.data_sources["macro_data"].update(data)
            
    def get_recent_queries(self, count=3):
        """Get the most recent user queries."""
        return self.query_history[-count:] if self.query_history else []
    
    def get_recent_responses(self, count=2):
        """Get the most recent LLM responses."""
        return self.llm_responses[-count:] if self.llm_responses else []
    
    def generate_context_summary(self):
        """Generate a summary of the conversation context for the LLM."""
        summary = "PREVIOUS CONVERSATION CONTEXT:\n"
        
        # Add recent queries and responses
        recent_exchanges = min(len(self.query_history), 2)  # Get up to 2 recent exchanges
        if recent_exchanges > 0:
            summary += "\nRecent exchanges:\n"
            start_idx = max(0, len(self.query_history) - recent_exchanges)
            for i in range(start_idx, len(self.query_history)):
                if i < len(self.llm_responses):
                    summary += f"User: {self.query_history[i]['text']}\n"
                    # Include a brief version of the response
                    response_text = self.llm_responses[i]['text']
                    if len(response_text) > 300:
                        response_text = response_text[:297] + "..."
                    summary += f"Assistant: {response_text}\n\n"
        
        # Add key data points from the most recent analysis
        if self.data_sources["macro_data"]:
            summary += "\nRecent macro data:\n"
            for key, value in self.data_sources["macro_data"].items():
                if key != "source" and not key.startswith("_"):
                    summary += f"- {key.replace('_', ' ').title()}: {value}\n"
        
        # Add historical analysis if available
        if self.data_sources["historical_analysis"].get("success", False):
            hist = self.data_sources["historical_analysis"]
            summary += f"\nRecent historical analysis: {hist.get('ticker', '')} on {hist.get('event_date', '')}\n"
            summary += f"- Price Change: {hist.get('price_change_pct', '')}%\n"
            
        # Add most relevant news articles
        if self.data_sources["news_sources"]:
            summary += "\nRecent news mentioned:\n"
            for i, news in enumerate(self.data_sources["news_sources"][:3], 1):
                summary += f"- {news.get('headline', '')}\n"
        
        return summary

    def is_follow_up_question(self, query):
        """Determine if a query is likely a follow-up question based on content."""
        if not self.query_history:
            return False
            
        # Check for reference to previous analysis
        follow_up_indicators = [
            # Pronouns and references
            r'\b(that|this|it|these|those)\b',
            r'\b(previous|earlier|above|mentioned)\b',
            r'\b(also|too|again|more)\b',
            
            # Questions that build on previous context
            r'\bwhy\b',
            r'\bhow (does|do|would|could|is|are)',
            r'\bwhat (about|if|else|other)\b',
            
            # Implicit references
            r'^(and|but|so)\b',
            r'^(can you|could you)',
            
            # Specific financial follow-ups
            r'\b(ticker|stock|market|trend)\b without explicit subject',
            r'\b(bullish|bearish)\b without context'
        ]
        
        for pattern in follow_up_indicators:
            if re.search(pattern, query.lower()):
                return True
                
        # Check if the query is very short (likely a follow-up)
        if len(query.split()) < 5:
            return True
            
        return False

# Add these utility functions to handle follow-up questions
def create_new_session():
    """Create a new conversation session."""
    session = ConversationContext()
    CONVERSATION_SESSIONS[session.session_id] = session
    return session

def get_session(session_id):
    """Get an existing session or create a new one."""
    if session_id and session_id in CONVERSATION_SESSIONS:
        return CONVERSATION_SESSIONS[session_id]
    return create_new_session()

def clean_old_sessions(max_age_hours=24):
    """Clean up old conversation sessions."""
    current_time = datetime.now()
    expired_sessions = []
    
    for session_id, session in CONVERSATION_SESSIONS.items():
        age = (current_time - session.creation_time).total_seconds() / 3600
        if age > max_age_hours:
            expired_sessions.append(session_id)
    
    for session_id in expired_sessions:
        del CONVERSATION_SESSIONS[session_id]
    
    return len(expired_sessions)

# Add this interactive mode function that can be used by Streamlit
def interactive_mode():
    """
    Run in interactive mode, allowing for continuous back-and-forth conversation.
    
    Returns:
        A function that can be called to process queries with conversation history.
    """
    active_session = create_new_session()
    
    def process_interactive_query(query, is_follow_up=None):
        """Process a query in interactive mode with conversation history."""
        nonlocal active_session
        
        # Process the query
        response, session_id = process_query(query, active_session.session_id, is_follow_up)
        
        # Update the active session
        if session_id:
            active_session = get_session(session_id)
        
        return response, active_session.session_id
    
    def reset_conversation():
        """Reset the conversation to start fresh."""
        nonlocal active_session
        active_session = create_new_session()
        return f"Conversation reset. New session ID: {active_session.session_id}"
    
    # Return the interactive functions that can be used by the UI
    return process_interactive_query, reset_conversation

if __name__ == "__main__":
    sys.exit(main()) 
