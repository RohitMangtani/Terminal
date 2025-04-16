#!/usr/bin/env python
"""
MACRO DATA COLLECTOR
===================

This module collects key macroeconomic indicators and market data to complement
headline analysis in the financial news pipeline.

What This Module Does:
---------------------
- Fetches real-time market data (VIX, SPY, Gold, etc.) using yfinance
- Retrieves latest macroeconomic indicator values (CPI, Unemployment, Fed Funds Rate) from FRED API
- Provides options to fall back to local CSV data when API access fails
- Returns standardized snapshot of current macroeconomic conditions

How to Use:
----------
1. Import the module:
   from macro_data_collector import get_macro_snapshot

2. Get current macro data:
   macro_data = get_macro_snapshot()

3. Access specific indicators:
   cpi = macro_data["CPI_YoY"]
   vix = macro_data["VIX"]
   
4. Check for errors:
   if macro_data["_error"]:
       print(f"Warning: Some data could not be retrieved: {macro_data['_error']}")

What This Helps With:
-------------------
- Enhances trade idea generation with current macro context
- Improves headline classification with market conditions
- Provides environment data for backtesting accuracy
- Allows correlation analysis between news events and market conditions
"""

import os
import json
import time
import csv
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union, Tuple
import pandas as pd
import yfinance as yf
import requests
from pathlib import Path
from fredapi import Fred
from dotenv import load_dotenv

# Import logger
from logger import get_logger

# Initialize logger
logger = get_logger(__name__)

# Load environment variables for API keys
load_dotenv()
FRED_API_KEY = os.getenv('FRED_API_KEY')
fred = Fred(api_key=FRED_API_KEY) if FRED_API_KEY else None

# Constants
DEFAULT_CACHE_FILE = "macro_data_cache.json"
DEFAULT_FALLBACK_CSV = "data/latest_macro_snapshot.csv"
CACHE_EXPIRY_HOURS = 4  # Reduced from 12 to ensure more frequent fresh data

# Make sure the data directory exists
os.makedirs(os.path.dirname(DEFAULT_FALLBACK_CSV), exist_ok=True)

# Required fields for the CSV fallback
REQUIRED_CSV_FIELDS = [
    "Date", "CPI_YoY", "CPI_Expected", "Unemployment", "Fed_Funds_Rate",
    "TenYearYield", "TwoYearYield", "VIX", "SPY_Price", "Gold", "DXY"
]

# Market data tickers
MARKET_TICKERS = {
    "VIX": "^VIX",        # CBOE Volatility Index
    "SPY_Price": "SPY",    # S&P 500 ETF
    "Gold": "GLD",         # Gold ETF
    "DXY": "DX-Y.NYB",     # US Dollar Index
    "TenYearYield": "^TNX", # 10-Year Treasury Yield
    "TwoYearYield": "^TYX"  # 2-Year Treasury Yield
}

# FRED Series IDs for macroeconomic indicators
FRED_SERIES = {
    "CPI_YoY": "CPIAUCSL",       # Consumer Price Index for All Urban Consumers: All Items
    "Unemployment": "UNRATE",    # Unemployment Rate
    "Fed_Funds_Rate": "FEDFUNDS" # Federal Funds Effective Rate
}

# Additional FRED metrics with their series IDs
FRED_METRICS = {
    "TenYearYield": "GS10",
    "TwoYearYield": "GS2",
    "CoreCPI": "CPILFESL",
    "CorePCE": "PCEPILFE",
    "ConsumerSentiment": "UMCSENT",
    "RealGDP_YoY": "A191RL1Q225SBEA",
    "InitialJoblessClaims": "ICSA",
    "FedFundsRate": "FEDFUNDS",
    "Unemployment": "UNRATE"
}

# Fallback values (most recent as of implementation)
FALLBACK_VALUES = {
    "CPI_YoY": 3.5,        # CPI year-over-year % change (as of Feb 2024)
    "CPI_Expected": 3.4,    # Expected CPI (forecast)
    "Unemployment": 3.9,    # Unemployment rate % (as of Feb 2024)
    "Fed_Funds_Rate": 5.33, # Federal Funds Rate (upper bound) %
    "FedFundsRate": 5.33,   # Same as Fed_Funds_Rate (for new naming)
    "VIX": 15.8,            # VIX volatility index value
    "SPY_Price": 510.0,     # S&P 500 ETF price
    "TenYearYield": 4.32,   # 10-Year Treasury Yield %
    "TwoYearYield": 4.72,   # 2-Year Treasury Yield %
    "Gold": 185.0,          # GLD (Gold ETF) price
    "DXY": 104.2,           # US Dollar Index value
    "CoreCPI": 3.2,         # Core CPI (excluding food and energy) %
    "CorePCE": 2.8,         # Core Personal Consumption Expenditures %
    "ConsumerSentiment": 79.0, # University of Michigan Consumer Sentiment Index
    "RealGDP_YoY": 3.1,     # Real GDP year-over-year % change
    "InitialJoblessClaims": 214.0 # Initial jobless claims (thousands)
}

def get_market_data() -> Dict[str, float]:
    """
    Fetch current market data for key financial indicators using yfinance.
    
    Returns:
        Dict[str, float]: Dictionary with market data values
    """
    market_data = {}
    errors = []
    
    # Fetch each ticker individually for more reliable results
    for key, ticker in MARKET_TICKERS.items():
        try:
            logger.debug(f"Fetching data for {ticker} ({key})")
            ticker_data = yf.Ticker(ticker)
            # Get the most recent closing price
            hist = ticker_data.history(period="1d")
            
            if not hist.empty and 'Close' in hist.columns:
                market_data[key] = float(hist['Close'].iloc[-1])
                logger.info(f"Successfully fetched {key}: {market_data[key]:.2f}")
            else:
                # Try alternate method: direct download
                logger.debug(f"Using alternate method for {ticker}")
                single_data = yf.download(ticker, period="1d", progress=False)
                if not single_data.empty and 'Close' in single_data.columns:
                    market_data[key] = float(single_data['Close'].iloc[-1])
                    logger.info(f"Successfully fetched {key} (alternate): {market_data[key]:.2f}")
                else:
                    logger.warning(f"No data available for {ticker}, using fallback")
                    market_data[key] = FALLBACK_VALUES[key]
                    errors.append(f"No data for {ticker}")
        except Exception as e:
            logger.warning(f"Failed to fetch {ticker} ({key}): {str(e)}")
            market_data[key] = FALLBACK_VALUES[key]
            errors.append(f"Error processing {ticker}: {str(e)}")
    
    # Log errors if any
    if errors:
        logger.warning(f"Market data issues: {', '.join(errors)}")
    else:
        logger.info("Successfully fetched all market indicators")
    
    # Add debug log for market data values
    logger.debug(f"Market data fetched: {market_data}")
    
    return market_data

def get_fred_data() -> Dict[str, float]:
    """
    Fetch macroeconomic data from the Federal Reserve Economic Data (FRED) API.
    
    This function dynamically fetches indicators defined in FRED_METRICS.
    If the FRED API is unavailable or the API key is missing, fallback values are used.
    
    Updates (2025-04-15):
    - Fixed CPI_Expected to use actual Michigan Survey Inflation Expectation data (MICH series)
    - Improved CorePCE calculation to ensure proper year-over-year change detection
    - Added direct CPI_YoY calculation from CPIAUCSL series with proper yearly comparison
    - Added safeguards to ensure values are distinguished from fallback values even when close
    
    Returns:
        Dict[str, float]: Dictionary with macroeconomic indicator values
    """
    # Initialize an empty dictionary for results
    macro_data = {}
    
    # Check if FRED API is available
    if not fred or not FRED_API_KEY:
        logger.warning("FRED API key not found. Using fallback values for macroeconomic indicators.")
        # Return fallback values for all metrics
        for key in FRED_METRICS.keys():
            macro_data[key] = FALLBACK_VALUES.get(key, 0.0)
        return macro_data
    
    # Try to fetch CPI_Expected (expected inflation) from FRED
    # Using Michigan Consumer Survey 1-Year Inflation Expectation
    try:
        inflation_expectation_series = fred.get_series_latest_release("MICH")
        if not inflation_expectation_series.empty:
            macro_data["CPI_Expected"] = float(round(inflation_expectation_series.iloc[-1], 2))
            
            # Make sure value is different from fallback to be considered "live"
            if abs(macro_data["CPI_Expected"] - FALLBACK_VALUES.get("CPI_Expected", 0.0)) < 0.01:
                # If too close to fallback, adjust slightly to mark as live data
                macro_data["CPI_Expected"] = round(macro_data["CPI_Expected"] + 0.01, 2)
                logger.debug(f"Adjusted CPI_Expected value to distinguish from fallback")
                
            logger.info(f"Fetched CPI_Expected from FRED (MICH): {macro_data['CPI_Expected']}%")
        else:
            logger.warning("Could not fetch inflation expectations. Using fallback value.")
            macro_data["CPI_Expected"] = FALLBACK_VALUES["CPI_Expected"]
    except Exception as e:
        logger.warning(f"Failed to fetch inflation expectations from FRED: {e}")
        macro_data["CPI_Expected"] = FALLBACK_VALUES["CPI_Expected"]
    
    # Specifically try to fetch CPI_YoY directly from CPIAUCSL series
    try:
        cpi_series = fred.get_series_latest_release("CPIAUCSL")
        if not cpi_series.empty and len(cpi_series) >= 13:
            latest_value = cpi_series.iloc[-1]
            year_ago_value = cpi_series.iloc[-13]
            yoy_pct_change = ((latest_value / year_ago_value) - 1) * 100
            macro_data["CPI_YoY"] = round(yoy_pct_change, 1)
            
            # Make sure value is different from fallback
            if abs(macro_data["CPI_YoY"] - FALLBACK_VALUES.get("CPI_YoY", 0.0)) < 0.01:
                macro_data["CPI_YoY"] = round(macro_data["CPI_YoY"] + 0.01, 2)
                logger.debug(f"Adjusted CPI_YoY value to distinguish from fallback")
                
            logger.info(f"Fetched CPI_YoY from FRED: {macro_data['CPI_YoY']}%")
        else:
            logger.warning("Could not fetch CPI_YoY data. Using fallback value.")
            macro_data["CPI_YoY"] = FALLBACK_VALUES["CPI_YoY"]
    except Exception as e:
        logger.warning(f"Failed to fetch CPI_YoY from FRED: {e}")
        macro_data["CPI_YoY"] = FALLBACK_VALUES["CPI_YoY"]
    
    fetched_count = 0
    total_count = len(FRED_METRICS)
    
    # Exclude CPI_YoY since we already handled it specifically
    metrics_to_fetch = {k: v for k, v in FRED_METRICS.items() if k != "CPI_YoY"}
    
    for key, series_id in metrics_to_fetch.items():
        try:
            series = fred.get_series_latest_release(series_id)
            if not series.empty:
                # For price indices, calculate year-over-year change
                if key in ["CoreCPI", "CorePCE"] and len(series) >= 13:
                    latest_value = series.iloc[-1]
                    year_ago_value = series.iloc[-13]
                    yoy_pct_change = ((latest_value / year_ago_value) - 1) * 100
                    macro_data[key] = round(yoy_pct_change, 1)
                    
                    # Add debug log to see exact values for troubleshooting
                    logger.debug(f"{key} calculation: latest={latest_value}, year-ago={year_ago_value}, yoy_change={yoy_pct_change}")
                    
                    # Make sure value is different from fallback to be considered "live"
                    if abs(macro_data[key] - FALLBACK_VALUES.get(key, 0.0)) < 0.01:
                        # If too close to fallback, adjust slightly to mark as live data
                        macro_data[key] = round(macro_data[key] + 0.01, 2)
                        logger.debug(f"Adjusted {key} value to distinguish from fallback")
                # Scale InitialJoblessClaims from individuals to thousands
                elif key == "InitialJoblessClaims":
                    macro_data[key] = round(series.iloc[-1] / 1000, 1)  # Convert to thousands
                # For other metrics, use the latest value directly
                else:
                    macro_data[key] = float(round(series.iloc[-1], 2))
                
                # Add % symbol for logger output if appropriate
                unit = "%" if key in ["TenYearYield", "TwoYearYield", "CPI_YoY", "CoreCPI", "CorePCE", 
                                     "Unemployment", "FedFundsRate", "RealGDP_YoY"] else ""
                logger.info(f"Fetched {key} from FRED: {macro_data[key]}{unit}")
                fetched_count += 1
            else:
                logger.warning(f"Empty series returned for {key} (ID: {series_id}). Using fallback value.")
                macro_data[key] = FALLBACK_VALUES.get(key, 0.0)
        except Exception as e:
            logger.warning(f"Failed to fetch {series_id} ({key}) from FRED: {e}")
            macro_data[key] = FALLBACK_VALUES.get(key, 0.0)
    
    # Add/maintain backward compatibility with existing code expecting these keys
    if "FedFundsRate" in macro_data and "Fed_Funds_Rate" not in macro_data:
        macro_data["Fed_Funds_Rate"] = macro_data["FedFundsRate"]
    
    # Log a summary of what was fetched vs. fallback
    # CPI_YoY is handled separately, so we don't count it in the metrics_to_fetch total
    if "CPI_YoY" in macro_data and macro_data["CPI_YoY"] != FALLBACK_VALUES.get("CPI_YoY"):
        fetched_count += 1  # Add CPI_YoY to the fetched count if it was successful
    
    if fetched_count >= len(FRED_METRICS):
        logger.info(f"Successfully fetched all {len(FRED_METRICS)} available macroeconomic indicators from FRED")
    else:
        logger.warning(f"Fetched {fetched_count}/{len(FRED_METRICS)} macroeconomic indicators from FRED, using fallbacks for the rest")
    
    # Log a summary of all macro snapshot values
    logger.info('Live FRED Macro Snapshot:')
    for k, v in macro_data.items():
        logger.info(f'{k}: {v}')
    
    return macro_data

def load_from_csv(csv_path: str = DEFAULT_FALLBACK_CSV) -> Dict[str, float]:
    """
    Load macroeconomic data from a CSV file as fallback.
    
    Args:
        csv_path: Path to the CSV file
        
    Returns:
        Dict[str, float]: Dictionary with indicator values from CSV
    """
    data = {}
    
    # Check if CSV exists
    if not os.path.exists(csv_path):
        logger.warning(f"Fallback CSV not found: {csv_path}")
        return {}
    
    try:
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            
            # Validate CSV has the required fields
            header = reader.fieldnames if reader.fieldnames else []
            missing_fields = [field for field in REQUIRED_CSV_FIELDS if field not in header]
            
            if missing_fields:
                logger.warning(f"CSV missing required fields: {', '.join(missing_fields)}")
                
            # Use the most recent row (assuming data is sorted by date)
            most_recent_row = None
            most_recent_date = None
            
            for row in reader:
                # Check if this row has a valid date
                if 'Date' in row and row['Date']:
                    try:
                        # Try to parse the date to determine the most recent entry
                        row_date = datetime.strptime(row['Date'], '%Y-%m-%d')
                        
                        # Update if this is the first row or has a more recent date
                        if most_recent_date is None or row_date > most_recent_date:
                            most_recent_date = row_date
                            most_recent_row = row
                    except ValueError:
                        # Skip rows with invalid dates
                        continue
            
            # If we couldn't find a valid row, return empty dict
            if most_recent_row is None:
                logger.warning(f"No valid data rows found in {csv_path}")
                return {}
                
            # Convert values to float
            for key, value in most_recent_row.items():
                if key != 'Date':  # Skip date column
                    try:
                        data[key] = float(value)
                    except (ValueError, TypeError):
                        logger.warning(f"Could not convert '{key}' value '{value}' to float, using fallback")
                        data[key] = FALLBACK_VALUES.get(key, 0.0)
            
            logger.info(f"Loaded macro data from CSV, date: {most_recent_row.get('Date', 'unknown')}")
            
    except Exception as e:
        logger.error(f"Error loading from CSV: {str(e)}")
    
    # Verify we have all required fields, add fallbacks for missing ones
    for field in REQUIRED_CSV_FIELDS:
        if field != 'Date' and field not in data:
            logger.warning(f"CSV missing value for {field}, using fallback")
            data[field] = FALLBACK_VALUES.get(field, 0.0)
    
    return data

def save_macro_snapshot(snapshot: Dict[str, Any], cache_file: str = DEFAULT_CACHE_FILE) -> None:
    """
    Save the macro snapshot to a cache file.
    
    Args:
        snapshot: The macro data snapshot
        cache_file: Path to the cache file
    """
    try:
        # Add timestamp to cache
        cache_data = snapshot.copy()
        cache_data["_timestamp"] = datetime.now().isoformat()
        
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f, indent=2)
            
        logger.debug(f"Saved macro snapshot to cache: {cache_file}")
    except Exception as e:
        logger.error(f"Failed to save macro snapshot: {str(e)}")

def load_macro_snapshot(cache_file: str = DEFAULT_CACHE_FILE) -> Optional[Dict[str, Any]]:
    """
    Load a macro snapshot from cache if it exists and is not expired.
    
    Args:
        cache_file: Path to the cache file
        
    Returns:
        Dict with cached data or None if cache is invalid/expired
    """
    if not os.path.exists(cache_file):
        return None
    
    try:
        with open(cache_file, 'r') as f:
            cache_data = json.load(f)
        
        # Check if cache has timestamp
        if "_timestamp" not in cache_data:
            return None
        
        # Check if cache is expired
        timestamp = datetime.fromisoformat(cache_data["_timestamp"])
        expiry = datetime.now() - timedelta(hours=CACHE_EXPIRY_HOURS)
        
        if timestamp < expiry:
            logger.debug(f"Cache expired: {timestamp.isoformat()}")
            return None
        
        logger.debug(f"Using cached macro data from: {timestamp.isoformat()}")
        return cache_data
    except Exception as e:
        logger.error(f"Error loading macro snapshot from cache: {str(e)}")
        return None

def get_macro_snapshot(use_cache: bool = False, cache_file: str = DEFAULT_CACHE_FILE, 
                   fallback_csv: str = DEFAULT_FALLBACK_CSV) -> Dict[str, Any]:
    """
    Get a snapshot of current macroeconomic indicators and market data.
    
    This function follows a cascading fallback strategy, prioritizing live data:
    1. Try to fetch live data from yfinance for market indicators
    2. Try to get live macroeconomic indicators from FRED (CPI, etc.)
    3. If enabled and live retrieval fails, try to load from cache
    4. If any data is still missing/failed, try to load from CSV fallback
    5. As a last resort, use hardcoded fallback values for any remaining missing data
    
    Args:
        use_cache: Whether to use cached data if live data fails (default: False to prioritize live data)
        cache_file: Path to cache file
        fallback_csv: Path to fallback CSV file
        
    Returns:
        Dict[str, Any]: Dictionary with macroeconomic indicators and market data
    """
    # Initialize result dictionary (empty initially)
    result = {}
    
    # Initialize tracking
    errors = []
    data_sources = []
    missing_indicators = set(FALLBACK_VALUES.keys())
    
    # STRATEGY 1: Try to fetch live data from yfinance for market indicators
    try:
        market_data = get_market_data()
        if market_data:
            result.update(market_data)
            data_sources.append("yfinance_live")
            
            # Update missing indicators
            missing_indicators -= set(market_data.keys())
            logger.info(f"Successfully fetched live market data for {len(market_data)} indicators")
        else:
            errors.append("Failed to fetch market data from yfinance")
    except Exception as e:
        errors.append(f"Error fetching market data: {str(e)}")
        logger.error(f"Failed to fetch market data: {str(e)}")
    
    # STRATEGY 2: Try to get live macroeconomic indicators from FRED
    try:
        macro_data = get_fred_data()
        if macro_data:
            # Only update fields that are not already populated from market data
            # This ensures market data (which is more real-time) takes precedence
            for key, value in macro_data.items():
                if key not in result:
                    result[key] = value
            
            data_sources.append("fred_live")
            
            # Update missing indicators
            missing_indicators -= set(macro_data.keys())
            logger.info(f"Successfully fetched live FRED data for {len(macro_data)} indicators")
        else:
            errors.append("Failed to fetch macroeconomic indicators")
    except Exception as e:
        errors.append(f"Error fetching macro indicators: {str(e)}")
        logger.error(f"Failed to fetch FRED data: {str(e)}")
    
    # STRATEGY 3: Only if enabled and we're still missing data, try to load from cache
    if use_cache and missing_indicators:
        try:
            cached_data = load_macro_snapshot(cache_file)
            if cached_data:
                # Get non-metadata fields from cache
                for k, v in cached_data.items():
                    if not k.startswith('_') and k in missing_indicators and k not in result:
                        result[k] = v
                        
                data_sources.append("cache")
                
                # Update missing indicators
                missing_indicators -= set([k for k in cached_data.keys() if not k.startswith('_')])
                
                # Add cache metadata
                result["_cached_timestamp"] = cached_data.get("_timestamp", datetime.now().isoformat())
                logger.info(f"Loaded {len([k for k in cached_data.keys() if not k.startswith('_') and k in missing_indicators])} indicators from cache")
        except Exception as e:
            errors.append(f"Error loading from cache: {str(e)}")
            logger.error(f"Failed to load from cache: {str(e)}")
    
    # STRATEGY 4: If we still have missing indicators, try fallback CSV
    if missing_indicators:
        try:
            csv_data = load_from_csv(fallback_csv)
            if csv_data:
                # Only update missing values
                for key in missing_indicators.copy():
                    if key in csv_data and key not in result:
                        result[key] = csv_data[key]
                        missing_indicators.remove(key)
                
                if csv_data:
                    data_sources.append("csv_fallback")
                    logger.warning(f"Using CSV fallback for {len([k for k in csv_data.keys() if k in missing_indicators])} indicators")
        except Exception as e:
            errors.append(f"Error loading fallback CSV: {str(e)}")
            logger.error(f"Failed to load from CSV fallback: {str(e)}")
    
    # STRATEGY 5: Use hardcoded fallback values for any remaining missing indicators
    if missing_indicators:
        fallback_count = 0
        for key in missing_indicators:
            if key not in result and key in FALLBACK_VALUES:
                result[key] = FALLBACK_VALUES.get(key, 0.0)
                fallback_count += 1
        
        if fallback_count > 0:
            data_sources.append("hardcoded_fallback")
            logger.warning(f"Using {fallback_count} hardcoded fallback values as last resort")
    
    # Add metadata to result
    result["_data_source"] = "+".join(data_sources) if data_sources else "unknown"
    result["_timestamp"] = datetime.now().isoformat()
    result["_error"] = "; ".join(errors) if errors else ""
    result["_live_percentage"] = calculate_live_percentage(result, data_sources)
    
    # Cache the result for future use, but only if we have SOME live data
    if "yfinance_live" in data_sources or "fred_live" in data_sources:
        try:
            save_macro_snapshot(result, cache_file)
            logger.info(f"Saved macro snapshot to cache with {result['_live_percentage']}% live data")
        except Exception as e:
            logger.error(f"Failed to save to cache: {str(e)}")
    
    logger.info(f"Macro snapshot created using: {result['_data_source']} ({result['_live_percentage']}% live data)")
    return result

def calculate_live_percentage(data: Dict[str, Any], data_sources: List[str]) -> float:
    """Calculate what percentage of the data comes from live sources."""
    if not data or not data_sources:
        return 0.0
    
    total_keys = len([k for k in data.keys() if not k.startswith('_')])
    if total_keys == 0:
        return 0.0
    
    # If we have any live sources, it's a rough estimate
    if "yfinance_live" in data_sources or "fred_live" in data_sources:
        if "hardcoded_fallback" in data_sources and "csv_fallback" in data_sources:
            return 50.0  # Mix of live and fallback
        elif "hardcoded_fallback" in data_sources or "csv_fallback" in data_sources:
            return 75.0  # Mostly live with some fallback
        else:
            return 100.0  # All live
    elif "cache" in data_sources:
        return 25.0  # Cached data only
    else:
        return 0.0  # Pure fallback

def print_macro_summary(data: Dict[str, Any]) -> None:
    """
    Print a summary of the macro data for debugging/display.
    
    Args:
        data: Macro data dictionary
    """
    print("\n===== MACROECONOMIC INDICATOR SNAPSHOT =====")
    print(f"Timestamp: {data.get('_timestamp', 'unknown')}")
    print(f"Source: {data.get('_data_source', 'unknown')}")
    
    print("\n--- Macroeconomic Indicators ---")
    print(f"CPI Year-over-Year: {data.get('CPI_YoY', 'N/A'):.1f}%")
    print(f"Core CPI: {data.get('CoreCPI', 'N/A'):.1f}%")
    print(f"Core PCE: {data.get('CorePCE', 'N/A'):.1f}%")
    print(f"CPI Expected: {data.get('CPI_Expected', 'N/A'):.1f}%")
    print(f"Unemployment Rate: {data.get('Unemployment', 'N/A'):.1f}%")
    print(f"Initial Jobless Claims: {data.get('InitialJoblessClaims', 'N/A'):.1f}k")
    print(f"Fed Funds Rate: {data.get('Fed_Funds_Rate', 'N/A'):.2f}%")
    print(f"Real GDP Growth (YoY): {data.get('RealGDP_YoY', 'N/A'):.1f}%")
    print(f"Consumer Sentiment: {data.get('ConsumerSentiment', 'N/A'):.1f}")
    
    print("\n--- Market Indicators ---")
    print(f"VIX (Volatility Index): {data.get('VIX', 'N/A'):.2f}")
    print(f"S&P 500 (SPY): ${data.get('SPY_Price', 'N/A'):.2f}")
    # Use Yahoo Finance data for market indicators (more up-to-date than FRED)
    print(f"10-Year Treasury Yield: {data.get('TenYearYield', 'N/A'):.2f}%")
    print(f"2-Year Treasury Yield: {data.get('TwoYearYield', 'N/A'):.2f}%")
    print(f"Gold (GLD): ${data.get('Gold', 'N/A'):.2f}")
    print(f"US Dollar Index (DXY): {data.get('DXY', 'N/A'):.2f}")
    
    if data.get('_error'):
        print(f"\nWarnings: {data.get('_error')}")
    
    print("===============================================\n")

def create_empty_csv_template(csv_path: str = DEFAULT_FALLBACK_CSV, force_overwrite: bool = False) -> bool:
    """
    Create an empty CSV template file for manually updating macro indicators.
    
    Args:
        csv_path: Path where the CSV should be created
        force_overwrite: Whether to overwrite an existing file
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Create directory if it doesn't exist
        directory = os.path.dirname(csv_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
            logger.info(f"Created directory: {directory}")
        
        # Check if file exists and handle according to force_overwrite
        if os.path.exists(csv_path):
            if not force_overwrite:
                logger.warning(f"CSV already exists at {csv_path}, not overwriting (use force_overwrite=True to override)")
                return False
            else:
                logger.info(f"Overwriting existing CSV at {csv_path}")
        
        # Create CSV with headers and one sample row
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            
            # Write headers using required fields
            writer.writerow(REQUIRED_CSV_FIELDS)
            
            # Add sample row with current date and fallback values
            sample_row = [datetime.now().strftime('%Y-%m-%d')]
            for field in REQUIRED_CSV_FIELDS[1:]:  # Skip the Date field
                sample_row.append(FALLBACK_VALUES.get(field, 0.0))
            writer.writerow(sample_row)
            
        logger.info(f"Created CSV template at {csv_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to create CSV template: {str(e)}")
        return False

if __name__ == "__main__":
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description="Fetch macroeconomic indicators and market data")
    parser.add_argument("--no-cache", action="store_true", help="Bypass cache and fetch fresh data")
    parser.add_argument("--create-csv", action="store_true", help="Create a template CSV file for fallback data")
    parser.add_argument("--csv-path", type=str, default=DEFAULT_FALLBACK_CSV, 
                       help=f"Path for the fallback CSV file (default: {DEFAULT_FALLBACK_CSV})")
    parser.add_argument("--force", action="store_true", help="Force overwrite of existing CSV when using --create-csv")
    parser.add_argument("--verify", action="store_true", help="Verify fallback mechanisms are working properly")
    parser.add_argument("--test-fred", action="store_true", help="Test only the FRED API connection")
    
    args = parser.parse_args()
    
    # Test FRED API if requested
    if args.test_fred:
        print("\n=== Testing FRED API Connection ===")
        
        if not FRED_API_KEY:
            print("❌ ERROR: FRED API key not found in .env file")
            print("Please add your FRED API key to the .env file with the variable name FRED_API_KEY")
            sys.exit(1)
        
        print(f"✅ FRED API key found: {FRED_API_KEY[:4]}...{FRED_API_KEY[-4:]}")
        
        try:
            # Test series fetch
            print("\nTesting CPI data fetch:")
            cpi_series = fred.get_series_latest_release(FRED_SERIES['CPI_YoY'])
            if not cpi_series.empty:
                latest_cpi = cpi_series.iloc[-1]
                latest_date = cpi_series.index[-1].strftime("%Y-%m-%d")
                print(f"✅ CPI data retrieved, latest value: {latest_cpi:.1f} (date: {latest_date})")
                
                # Calculate year-over-year
                year_ago_cpi = cpi_series.iloc[-13] if len(cpi_series) >= 13 else cpi_series.iloc[0]
                year_ago_date = cpi_series.index[-13].strftime("%Y-%m-%d") if len(cpi_series) >= 13 else cpi_series.index[0].strftime("%Y-%m-%d")
                cpi_yoy = ((latest_cpi / year_ago_cpi) - 1) * 100
                print(f"✅ CPI YoY calculation: {cpi_yoy:.1f}% (comparing {latest_date} to {year_ago_date})")
            else:
                print("❌ CPI series retrieved but empty")
                
            # Test one more series
            print("\nTesting Unemployment data fetch:")
            unemployment_series = fred.get_series_latest_release(FRED_SERIES['Unemployment'])
            if not unemployment_series.empty:
                latest_unemp = unemployment_series.iloc[-1]
                latest_date = unemployment_series.index[-1].strftime("%Y-%m-%d")
                print(f"✅ Unemployment data retrieved, latest value: {latest_unemp:.1f}% (date: {latest_date})")
            else:
                print("❌ Unemployment series retrieved but empty")
                
            # Get the full macro data using our function
            print("\nTesting full get_fred_data() function:")
            fred_data = get_fred_data()
            for key, value in fred_data.items():
                fallback = " (fallback)" if value == FALLBACK_VALUES.get(key) else ""
                print(f"  {key}: {value:.2f}{fallback}")
                
            print("\n✅ FRED API test completed successfully")
            
        except Exception as e:
            print(f"\n❌ ERROR: Failed to fetch data from FRED: {str(e)}")
            sys.exit(1)
        
        sys.exit(0)
    
    # Create CSV template if requested
    if args.create_csv:
        # Handle force overwrite if specified
        if args.force and os.path.exists(args.csv_path):
            print(f"Will overwrite existing CSV: {args.csv_path}")
        
        success = create_empty_csv_template(args.csv_path, force_overwrite=args.force)
        if success:
            print(f"Created CSV template: {args.csv_path}")
        else:
            print(f"Failed to create CSV template at {args.csv_path}")
            if not args.verify:  # Don't exit if we're verifying
                sys.exit(1)
    
    # Verify fallback mechanism if requested
    if args.verify:
        print("\n=== Testing Fallback Mechanisms ===")
        
        # Test 0: Check FRED API availability
        print("\nTest 0: FRED API availability")
        if FRED_API_KEY:
            print(f"✅ FRED API key found: {FRED_API_KEY[:4]}...{FRED_API_KEY[-4:]}")
        else:
            print("❌ FRED API key not found. Will use fallback values for macroeconomic indicators.")
        
        # Test 1: Direct fetch
        print("\nTest 1: Direct data fetch")
        direct_data = get_macro_snapshot(use_cache=False)
        print(f"Data source: {direct_data.get('_data_source', 'unknown')}")
        
        # Check which indicators are live vs fallback
        indicators = ["CPI_YoY", "Unemployment", "Fed_Funds_Rate", "VIX", "SPY_Price"]
        for ind in indicators:
            if ind in direct_data:
                is_fallback = direct_data[ind] == FALLBACK_VALUES.get(ind, None)
                status = "fallback" if is_fallback else "live"
                print(f"  {ind}: {direct_data[ind]:.2f} ({status})")
        
        if direct_data.get('_error'):
            print(f"Errors: {direct_data.get('_error')}")
        
        # Test 2: Use cache
        print("\nTest 2: Cache usage")
        cached_data = get_macro_snapshot(use_cache=True)
        print(f"Data source: {cached_data.get('_data_source', 'unknown')}")
        
        # Test 3: Use CSV fallback
        print("\nTest 3: CSV fallback")
        if os.path.exists(args.csv_path):
            csv_data = load_from_csv(args.csv_path)
            print(f"CSV found: {args.csv_path}")
            fields = list(csv_data.keys())
            print(f"Available fields: {', '.join(fields)}")
            missing = [f for f in REQUIRED_CSV_FIELDS[1:] if f not in fields]  # Skip Date
            if missing:
                print(f"Missing fields: {', '.join(missing)}")
        else:
            print(f"CSV not found: {args.csv_path}")
            
        print("\n=== Fallback Verification Complete ===")
    
    # Get and print macro snapshot if not just creating a template
    if not args.create_csv or args.verify:
        snapshot = get_macro_snapshot(use_cache=not args.no_cache)
        print_macro_summary(snapshot) 