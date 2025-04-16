import yfinance as yf
import pandas as pd
import numpy as np
import json
import os
import re
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional, Union
from pandas.tseries.offsets import BDay

# Default number of events to return
DEFAULT_TOP_N = 3
# Number of trading days to analyze after event
DEFAULT_ANALYSIS_DAYS = 7
# Default ticker for general market conditions
DEFAULT_MARKET_TICKER = "SPY"
# Path to event templates file
TEMPLATES_FILE = "historical_event_templates.json"
# API endpoint for historical event matching (placeholder, will be implemented with free API)
EVENTS_API_ENDPOINT = "https://api.events.example.com/match"
# Flag to use AI for event matching instead of static templates
USE_AI_MATCHING = True
# Set to True to enable debug output
DEBUG = False
# Known problematic tickers - empty now since we'll fix format
UNSUPPORTED_TICKERS = []
# Strings that indicate crypto assets (which need special handling)
CRYPTO_INDICATORS = ["BTC", "ETH", "XRP", "COIN", "CRYPTO", "USDT", "USDC", "DOT", "ADA", "SOL", "DOGE"]
# Common crypto symbols to standardize
COMMON_CRYPTOS = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "XRP": "XRP-USD",
    "DOGE": "DOGE-USD",
    "ADA": "ADA-USD",
    "SOL": "SOL-USD",
    "DOT": "DOT-USD",
    "USDT": "USDT-USD",
    "USDC": "USDC-USD",
    "LINK": "LINK-USD",
    "LTC": "LTC-USD"
}
# Common crypto symbols and their Yahoo Finance format
CRYPTO_FORMATS = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "XRP": "XRP-USD",
    "DOGE": "DOGE-USD",
    "USDT": "USDT-USD",
}

def standardize_ticker(ticker: str) -> str:
    """
    Standardize ticker symbols, especially for cryptocurrencies.
    Uses free API for comprehensive ticker mapping when available.
    
    Args:
        ticker (str): Original ticker symbol
        
    Returns:
        str: Standardized ticker symbol
    """
    # Standardize ticker to uppercase
    ticker = ticker.upper()
    
    # Direct mapping for common cryptos
    if ticker in CRYPTO_FORMATS:
        return CRYPTO_FORMATS[ticker]
    
    # Handle BTCUSD -> BTC-USD format
    if "USD" in ticker:
        for crypto in CRYPTO_FORMATS:
            if crypto in ticker:
                return f"{crypto}-USD"
    
    # Try to use free financial symbol API to standardize ticker
    try:
        # This is a placeholder for a real API call to a free financial symbol service
        # You would replace this with an actual integration to a free API
        # Example API providers: Alpha Vantage (free tier), Financial Modeling Prep (free tier)
        # api_url = f"https://api.example.com/symbols/standardize?symbol={ticker}"
        # response = requests.get(api_url)
        # if response.status_code == 200:
        #     standardized = response.json().get('standardized_symbol')
        #     if standardized:
        #         return standardized
        pass
    except Exception as e:
        print(f"Error standardizing ticker via API: {str(e)}")
    
    # If no transformations needed or API fails, return original
    return ticker

def fetch_market_data(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Fetch daily OHLC market data for a given ticker and date range.
    Uses yfinance as primary source with built-in fallback options.
    
    Args:
        ticker (str): The ticker symbol
        start_date (str): Start date in YYYY-MM-DD format
        end_date (str): End date in YYYY-MM-DD format
        
    Returns:
        pd.DataFrame: DataFrame with daily market data
    """
    # Standardize the ticker symbol (especially for crypto)
    original_ticker = ticker
    ticker = standardize_ticker(ticker)
    
    if original_ticker != ticker:
        print(f"Converted ticker {original_ticker} to Yahoo Finance format: {ticker}")
    
    # Check for unsupported tickers (empty list now but keep for future)
    if ticker.upper() in UNSUPPORTED_TICKERS:
        print(f"Warning: Ticker {ticker} is known to be unsupported, skipping")
        return pd.DataFrame()
    
    # Special handling for crypto assets
    is_crypto = False
    if "-" in ticker and any(crypto in ticker.upper() for crypto in CRYPTO_INDICATORS):
        is_crypto = True
        print(f"Processing cryptocurrency ticker: {ticker}")
    
    try:
        # Fetch data from yfinance
        df = yf.download(ticker, start=start_date, end=end_date, progress=False)
        
        # Check if df is None or empty
        if df is None or df.empty:
            print(f"No data found for ticker {ticker} in specified date range")
            
            # For crypto assets, try alternative format if the first attempt failed
            if not is_crypto and any(crypto in original_ticker.upper() for crypto in CRYPTO_INDICATORS):
                crypto_ticker = f"{original_ticker.upper().replace('USD', '')}-USD"
                print(f"Trying alternative crypto format: {crypto_ticker}")
                df = yf.download(crypto_ticker, start=start_date, end=end_date, progress=False)
                
                if df is None or df.empty:
                    print(f"Still no data for alternative format {crypto_ticker}")
                    return pd.DataFrame()
                else:
                    print(f"Successfully fetched data using alternative format {crypto_ticker}")
                    ticker = crypto_ticker
            else:
                # Try alternate free financial APIs as backup
                try:
                    # This is a placeholder for integration with another free API
                    # Example providers with free tiers: Alpha Vantage, IEX Cloud, Financial Modeling Prep
                    # api_url = f"https://api.example.com/historical?symbol={ticker}&start={start_date}&end={end_date}"
                    # response = requests.get(api_url)
                    # if response.status_code == 200:
                    #     data = response.json()
                    #     # Convert API response to pandas DataFrame
                    #     # df = pd.DataFrame(data['prices'])
                    #     # return df
                    pass
                except Exception as e:
                    print(f"Error fetching data from backup API: {str(e)}")
                    return pd.DataFrame()
                    
                return pd.DataFrame()
            
        # Debug output - show the data retrieved
        if DEBUG:
            print(f"Data fetched for {ticker} from {start_date} to {end_date}:")
            print(df[['Open', 'High', 'Low', 'Close']].head())
            print(f"Total rows: {len(df)}")
            
        # Verify that required 'Close' column exists
        if 'Close' not in df.columns:
            print(f"Warning: Downloaded data for {ticker} missing 'Close' column")
            return pd.DataFrame()
            
        return df
    except Exception as e:
        print(f"Error fetching data for {ticker}: {str(e)}")
        return pd.DataFrame()

def calculate_drop_percentage(df: pd.DataFrame) -> Tuple[float, float]:
    """
    Calculate both the overall price change and maximum drawdown within the dataframe period.
    
    Args:
        df (pd.DataFrame): DataFrame with market data including 'Close' column
        
    Returns:
        Tuple[float, float]: (overall_change_pct, max_drawdown_pct)
        - overall_change_pct: Percentage change from first to last close (positive is gain, negative is drop)
        - max_drawdown_pct: Maximum percentage drawdown during the period (always negative or zero)
    """
    if df.empty or 'Close' not in df.columns or len(df) < 2:
        print("Warning: Insufficient data for price change calculation")
        return 0.0, 0.0
    
    try:
        # Extract close prices
        closes = df['Close'].values
        
        # Calculate overall change percentage
        first_close = closes[0]
        last_close = closes[-1]
        overall_change_pct = ((last_close / first_close) - 1.0) * 100
        
        # Calculate maximum drawdown (peak to trough)
        peak = closes[0]
        max_drawdown = 0.0
        
        for close in closes[1:]:
            peak = max(peak, close)
            current_drawdown = (close / peak - 1.0) * 100
            max_drawdown = min(max_drawdown, current_drawdown)
        
        # Convert from numpy array/value to float if needed
        if hasattr(overall_change_pct, 'item'):
            overall_change_pct = overall_change_pct.item()
        if hasattr(max_drawdown, 'item'):
            max_drawdown = max_drawdown.item()
            
        return float(overall_change_pct), float(max_drawdown)
    except Exception as e:
        print(f"Error calculating price change: {str(e)}")
        return 0.0, 0.0

def load_historical_events() -> List[Dict[str, Any]]:
    """
    Load historical events from templates file or fetch from API.
    Uses local cache with the option to pull fresh data from a free API.
    
    Returns:
        List[Dict[str, Any]]: List of historical event dictionaries
    """
    events = []
    
    # Try loading from local file first (as cache)
    try:
        if os.path.exists(TEMPLATES_FILE):
            with open(TEMPLATES_FILE, 'r') as f:
                events = json.load(f)
                if events:
                    print(f"Loaded {len(events)} historical events from local cache")
                    return events
    except Exception as e:
        print(f"Error loading historical events from local cache: {str(e)}")
    
    # If local file doesn't exist or is empty, try to fetch from API
    try:
        # This is a placeholder for integration with a free historical events API
        # Example approach: use a free news API with historical access like GNews API
        # api_url = "https://api.example.com/historical_events"
        # response = requests.get(api_url)
        # if response.status_code == 200:
        #     events = response.json()
        #     
        #     # Save to local cache for future use
        #     with open(TEMPLATES_FILE, 'w') as f:
        #         json.dump(events, f, indent=2)
        #     
        #     print(f"Fetched {len(events)} historical events from API")
        #     return events
        
        # For now, return empty list if we can't fetch events
        print("Warning: Could not fetch historical events from API")
        return []
    except Exception as e:
        print(f"Error fetching historical events from API: {str(e)}")
        return []

def ai_match_events(classified_headline: Dict[str, Any], top_n: int = DEFAULT_TOP_N) -> List[Dict[str, Any]]:
    """
    Use AI to match current headline with similar historical events.
    This replaces static template matching with dynamic AI-based matching.
    
    Args:
        classified_headline (Dict[str, Any]): The classified headline
        top_n (int): Number of top matches to return
        
    Returns:
        List[Dict[str, Any]]: List of matched historical events
    """
    try:
        # First try to use OpenAI API (replace with any available AI service)
        # This integration would use a prompt like:
        # "Find historical market events similar to: {headline['title']}
        #  Event type: {headline['event_type']}
        #  Sentiment: {headline['sentiment']}
        #  Sector: {headline['sector']}"
        
        # For development, fallback to traditional matching
        return match_similar_events(classified_headline, top_n)
    except Exception as e:
        print(f"Error in AI event matching: {str(e)}")
        # Fallback to traditional matching
        return match_similar_events(classified_headline, top_n)

def calculate_match_score(headline: Dict[str, Any], template: Dict[str, Any]) -> float:
    """
    Calculate a match score between a headline and a historical event template.
    
    Args:
        headline (Dict[str, Any]): Classified headline
        template (Dict[str, Any]): Historical event template
        
    Returns:
        float: Match score (0.0 to 1.0)
    """
    score = 0.0
    
    # Match event_type (highest weight)
    if headline.get('event_type') == template.get('event_type'):
        score += 0.5
    
    # Match sentiment (medium weight)
    if headline.get('sentiment') == template.get('sentiment'):
        score += 0.3
    
    # Match sector (lower weight)
    if headline.get('sector') == template.get('sector'):
        score += 0.2
    
    return score

def match_similar_events(classified_headline: Dict[str, Any], top_n: int = DEFAULT_TOP_N) -> List[Dict[str, Any]]:
    """
    Find similar historical events based on event type, sentiment, and sector.
    
    Args:
        classified_headline (Dict[str, Any]): The classified headline
        top_n (int): Number of top matches to return
        
    Returns:
        List[Dict[str, Any]]: List of matched historical events
    """
    # Load historical events
    historical_events = load_historical_events()
    
    if not historical_events:
        return []
    
    # Calculate match scores for each historical event
    scored_events = []
    for event in historical_events:
        score = calculate_match_score(classified_headline, event)
        if score > 0:
            scored_events.append((score, event))
    
    # Sort by score (descending) and take top N
    scored_events.sort(reverse=True, key=lambda x: x[0])
    top_events = scored_events[:top_n]
    
    # Prepare result with proper structure
    results = []
    for score, event in top_events:
        try:
            # Calculate the market impact for this event
            impact_data = analyze_market_impact(event)
            
            # Format the result
            result = {
                "event_summary": event.get("event_summary", ""),
                "match_score": round(score, 2),
                "affected_ticker": event.get("affected_ticker", DEFAULT_MARKET_TICKER),
                "price_change_pct": impact_data["price_change_pct"],
                "max_drawdown_pct": impact_data["max_drawdown_pct"],
                "event_date": event.get("event_date", ""),
                "date_range": impact_data["date_range"],
                "price_data": impact_data["price_data"]
            }
            results.append(result)
        except Exception as e:
            print(f"Error processing event '{event.get('event_summary', 'Unknown')}': {str(e)}")
            # Still include the event but mark the impact as unavailable
            result = {
                "event_summary": event.get("event_summary", ""),
                "match_score": round(score, 2),
                "affected_ticker": event.get("affected_ticker", DEFAULT_MARKET_TICKER),
                "price_change_pct": "N/A (processing error)",
                "max_drawdown_pct": "N/A (processing error)",
                "event_date": event.get("event_date", ""),
                "date_range": "N/A",
                "price_data": {}
            }
            results.append(result)
    
    return results

def analyze_market_impact(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze the market impact of a historical event.
    
    Args:
        event (Dict[str, Any]): Historical event data
        
    Returns:
        Dict[str, Any]: Dictionary with market impact data and price information
    """
    ticker = event.get("affected_ticker", DEFAULT_MARKET_TICKER)
    event_date = event.get("event_date", "")
    
    if not event_date:
        print(f"Warning: Missing event date for '{event.get('event_summary', 'Unknown event')}'")
        return {"price_change_pct": "N/A", "max_drawdown_pct": "N/A", "date_range": "N/A", "price_data": {}}
    
    # Convert to datetime
    try:
        event_datetime = datetime.strptime(event_date, "%Y-%m-%d")
    except ValueError:
        print(f"Invalid date format for event: {event.get('event_summary')}")
        return {"price_change_pct": "N/A", "max_drawdown_pct": "N/A", "date_range": "N/A", "price_data": {}}
    
    # Calculate end date (adding enough days to ensure we have 7 trading days)
    end_datetime = event_datetime + timedelta(days=14)
    end_date = end_datetime.strftime("%Y-%m-%d")
    
    # Fetch market data
    df = fetch_market_data(ticker, event_date, end_date)
    
    if DEBUG:
        print(f"Analyzing market impact for {event.get('event_summary')} ({event_date}):")
        print(f"Ticker: {ticker}, Trading days analyzed: {len(df)}")
        
    if df.empty:
        print(f"Warning: No market data available for {ticker} from {event_date} to {end_date}")
        return {"price_change_pct": "N/A", "max_drawdown_pct": "N/A", "date_range": "N/A", "price_data": {}}
    
    # Capture actual date range from the data
    actual_start_date = df.index[0].strftime("%Y-%m-%d")
    actual_end_date = df.index[-1].strftime("%Y-%m-%d")
    date_range = f"{actual_start_date} to {actual_end_date}"
    
    # Extract price data - fix FutureWarnings by using proper Series access methods
    first_price = df['Close'].iloc[0]
    if isinstance(first_price, (pd.Series, pd.DataFrame)):
        first_price = first_price.iloc[0]
    
    last_price = df['Close'].iloc[-1]
    if isinstance(last_price, (pd.Series, pd.DataFrame)):
        last_price = last_price.iloc[0]
    
    lowest_price = df['Low'].min()
    if isinstance(lowest_price, (pd.Series, pd.DataFrame)):
        lowest_price = lowest_price.iloc[0]
    
    highest_price = df['High'].max()
    if isinstance(highest_price, (pd.Series, pd.DataFrame)):
        highest_price = highest_price.iloc[0]
    
    # Prepare price data dictionary
    price_data = {
        "start_price": first_price,
        "end_price": last_price,
        "lowest_price": lowest_price,
        "highest_price": highest_price,
        "trading_days": len(df)
    }
    
    # Limit to the specified number of trading days
    if len(df) > DEFAULT_ANALYSIS_DAYS:
        df = df.head(DEFAULT_ANALYSIS_DAYS)
    
    # Calculate price change and maximum drawdown percentages
    price_change_pct, max_drawdown_pct = calculate_drop_percentage(df)
    
    return {
        "price_change_pct": price_change_pct,
        "max_drawdown_pct": max_drawdown_pct,
        "date_range": date_range,
        "price_data": price_data
    }

def find_similar_historical_events(headline: Dict[str, Any], top_n: int = DEFAULT_TOP_N) -> List[Dict[str, Any]]:
    """
    Main function to find similar historical events and their market impacts.
    Uses AI matching when enabled, otherwise falls back to template matching.
    
    Args:
        headline (Dict[str, Any]): The classified headline
        top_n (int): Number of top matches to return
        
    Returns:
        List[Dict[str, Any]]: List of similar events with market impact data
    """
    if USE_AI_MATCHING:
        return ai_match_events(headline, top_n)
    else:
        return match_similar_events(headline, top_n)

def set_debug_mode(enable: bool = True) -> None:
    """
    Enable or disable debug output.
    
    Args:
        enable (bool): True to enable debug output, False to disable
    """
    global DEBUG
    DEBUG = enable

if __name__ == "__main__":
    # Enable debug mode for direct runs
    set_debug_mode(True)
    
    # Example usage
    test_headline = {
        "title": "Fed signals potential rate cut on cooling inflation",
        "event_type": "Monetary Policy",
        "sentiment": "Bullish",
        "sector": "Financials"
    }
    
    matches = find_similar_historical_events(test_headline)
    
    print(f"Similar historical events for: {test_headline['title']}")
    print("-" * 80)
    
    for i, match in enumerate(matches, 1):
        print(f"{i}. {match['event_summary']}")
        print(f"   Match score: {match['match_score']}")
        print(f"   Event date: {match['event_date']}")
        print(f"   Affected ticker: {match['affected_ticker']}")
        print(f"   Date range analyzed: {match['date_range']}")
        
        # Format the change percentage based on type
        price_change = match.get('price_change_pct')
        if isinstance(price_change, (int, float)):
            print(f"   Overall price change: {price_change:.2f}%")
        else:
            print(f"   Overall price change: {price_change}")
            
        # Format the drawdown percentage based on type
        max_drawdown = match.get('max_drawdown_pct')
        if isinstance(max_drawdown, (int, float)):
            print(f"   Maximum drawdown: {max_drawdown:.2f}%")
        else:
            print(f"   Maximum drawdown: {max_drawdown}")
        
        # Display price data if available
        if match.get('price_data'):
            pd = match['price_data']
            print(f"   Price data:")
            print(f"     Start price: ${pd.get('start_price', 'N/A'):.2f}")
            print(f"     End price: ${pd.get('end_price', 'N/A'):.2f}")
            print(f"     Highest price: ${pd.get('highest_price', 'N/A'):.2f}")
            print(f"     Lowest price: ${pd.get('lowest_price', 'N/A'):.2f}")
            print(f"     Trading days analyzed: {pd.get('trading_days', 'N/A')}")
        
        print() 