#!/usr/bin/env python
"""
OPTIONS DATA COLLECTOR
=====================

What This Module Does:
--------------------
This module fetches real-time options market metrics for a given stock ticker.
It provides functions to retrieve various options data including implied volatility,
put-call ratio, and open interest.

How to Use:
----------
1. Get options snapshot:
   from options_data_collector import get_options_snapshot
   options_data = get_options_snapshot("AAPL")

2. Access specific metrics:
   atm_iv = options_data["IV_atm"]
   skew = options_data["IV_skew"]
   
What This Helps You See:
-----------------------
- Implied volatility levels and skew (market's expectation of future volatility)
- Options market sentiment via put-call ratio
- Trading activity and liquidity via open interest
- Supply/demand dynamics in the options market
"""

import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import warnings
from typing import Dict, Any, Optional, List, Tuple
import time
import math

# Constants
DEFAULT_EXP_WINDOW = 30  # Default expiration window (days)
DEFAULT_OTM_PCT = 0.05   # Default OTM percentage (5%)
CACHE_TIMEOUT = 300      # Cache timeout in seconds (5 minutes)

# Cache for options data to avoid excessive API calls
_options_cache = {}

def get_options_snapshot(ticker: str, exp_window: int = DEFAULT_EXP_WINDOW, 
                         otm_pct: float = DEFAULT_OTM_PCT, use_cache: bool = True) -> Dict[str, Any]:
    """
    Get a snapshot of options market metrics for a given ticker.
    
    Args:
        ticker: Stock ticker symbol (e.g., "AAPL")
        exp_window: Target expiration window in days (default: 30)
        otm_pct: Out-of-the-money percentage for IV comparison (default: 5%)
        use_cache: Whether to use cached data if available and not expired
        
    Returns:
        Dictionary containing options metrics:
        {
            "IV_atm": Float (at-the-money implied volatility),
            "IV_put_5pct_OTM": Float (5% OTM put implied volatility),
            "IV_call_5pct_OTM": Float (5% OTM call implied volatility),
            "IV_skew": Float (put_iv - call_iv, higher values indicate downside protection demand),
            "put_call_ratio": Float (put volume/call volume, higher values indicate bearish sentiment),
            "open_interest_total": Int (total open contracts),
            "open_interest_change": Int (change in open interest from previous period)
        }
    """
    global _options_cache
    
    # Check cache first if enabled
    cache_key = f"{ticker}_{exp_window}_{otm_pct}"
    current_time = time.time()
    
    if use_cache and cache_key in _options_cache:
        cache_entry = _options_cache[cache_key]
        if current_time - cache_entry["timestamp"] < CACHE_TIMEOUT:
            return cache_entry["data"]
    
    # Initialize empty results dictionary with default values
    result = {
        "IV_atm": None,
        "IV_put_5pct_OTM": None,
        "IV_call_5pct_OTM": None,
        "IV_skew": None,
        "put_call_ratio": None,
        "open_interest_total": None,
        "open_interest_change": None
    }
    
    try:
        # Get the stock data
        stock = yf.Ticker(ticker)
        
        # Get current stock price
        current_price = stock.info.get("regularMarketPrice", stock.info.get("previousClose"))
        if not current_price:
            warnings.warn(f"Could not get current price for {ticker}")
            return result
        
        # Find the appropriate expiration date (closest to target window)
        target_date = datetime.datetime.now() + datetime.timedelta(days=exp_window)
        expiration_dates = stock.options
        
        if not expiration_dates:
            warnings.warn(f"No options data available for {ticker}")
            return result
        
        # Convert to datetime objects and find closest to target
        exp_datetime = [datetime.datetime.strptime(date, '%Y-%m-%d') for date in expiration_dates]
        closest_exp = min(exp_datetime, key=lambda x: abs((x - target_date).days))
        closest_exp_str = closest_exp.strftime('%Y-%m-%d')
        
        # Get options chain for the closest expiration date
        options = stock.option_chain(closest_exp_str)
        calls = options.calls
        puts = options.puts
        
        # Calculate target strikes for ATM and OTM options
        atm_strike = find_closest_strike(calls, current_price)
        otm_call_strike = find_closest_strike(calls, current_price * (1 + otm_pct))
        otm_put_strike = find_closest_strike(puts, current_price * (1 - otm_pct))
        
        # Get implied volatilities
        atm_iv = get_iv_for_strike(calls, atm_strike)
        call_otm_iv = get_iv_for_strike(calls, otm_call_strike)
        put_otm_iv = get_iv_for_strike(puts, otm_put_strike)
        
        # Calculate IV skew
        iv_skew = put_otm_iv - call_otm_iv if put_otm_iv and call_otm_iv else None
        
        # Calculate put-call ratio (based on volume)
        total_call_volume = calls['volume'].sum() if 'volume' in calls.columns else 0
        total_put_volume = puts['volume'].sum() if 'volume' in puts.columns else 0
        
        if total_call_volume > 0:
            put_call_ratio = total_put_volume / total_call_volume
        else:
            put_call_ratio = None
        
        # Calculate open interest
        total_open_interest = (
            calls['openInterest'].sum() if 'openInterest' in calls.columns else 0
        ) + (
            puts['openInterest'].sum() if 'openInterest' in puts.columns else 0
        )
        
        # For open interest change, we'd need historical data which isn't directly available
        # For now, we'll use None or implement a local tracking mechanism in the future
        open_interest_change = None
        
        # Populate result dictionary
        result = {
            "IV_atm": atm_iv,
            "IV_put_5pct_OTM": put_otm_iv,
            "IV_call_5pct_OTM": call_otm_iv,
            "IV_skew": iv_skew,
            "put_call_ratio": put_call_ratio,
            "open_interest_total": total_open_interest,
            "open_interest_change": open_interest_change
        }
        
        # Update cache
        _options_cache[cache_key] = {
            "timestamp": current_time,
            "data": result
        }
        
        return result
        
    except Exception as e:
        warnings.warn(f"Error fetching options data for {ticker}: {str(e)}")
        return result

def find_closest_strike(options_df: pd.DataFrame, target_price: float) -> float:
    """
    Find the strike price closest to the target price.
    
    Args:
        options_df: DataFrame containing options data
        target_price: Target price to find closest strike to
        
    Returns:
        Closest strike price
    """
    if 'strike' not in options_df.columns or options_df.empty:
        return None
        
    return options_df.iloc[(options_df['strike'] - target_price).abs().argsort()[0]]['strike']

def get_iv_for_strike(options_df: pd.DataFrame, strike: float) -> Optional[float]:
    """
    Get the implied volatility for a specific strike price.
    
    Args:
        options_df: DataFrame containing options data
        strike: Strike price to get IV for
        
    Returns:
        Implied volatility as decimal (not percentage)
    """
    if strike is None or 'impliedVolatility' not in options_df.columns:
        return None
        
    matching_options = options_df[options_df['strike'] == strike]
    if matching_options.empty:
        return None
        
    return matching_options.iloc[0]['impliedVolatility']

def clear_cache():
    """
    Clear the options data cache.
    """
    global _options_cache
    _options_cache = {}

def print_options_summary(options_data: Dict[str, Any]) -> None:
    """
    Print a human-readable summary of options metrics.
    
    Args:
        options_data: Dictionary of options data from get_options_snapshot
    """
    print("\n=== OPTIONS MARKET METRICS ===")
    
    # Format implied volatility as percentage
    if options_data["IV_atm"] is not None:
        print(f"ATM Implied Volatility: {options_data['IV_atm'] * 100:.2f}%")
    else:
        print("ATM Implied Volatility: Not available")
        
    if options_data["IV_call_5pct_OTM"] is not None:
        print(f"5% OTM Call IV: {options_data['IV_call_5pct_OTM'] * 100:.2f}%")
    else:
        print("5% OTM Call IV: Not available")
        
    if options_data["IV_put_5pct_OTM"] is not None:
        print(f"5% OTM Put IV: {options_data['IV_put_5pct_OTM'] * 100:.2f}%")
    else:
        print("5% OTM Put IV: Not available")
    
    # IV skew indicates demand for downside protection
    if options_data["IV_skew"] is not None:
        skew_value = options_data["IV_skew"] * 100
        skew_interpretation = "high" if skew_value > 3 else "moderate" if skew_value > 1 else "low"
        print(f"IV Skew: {skew_value:.2f}% ({skew_interpretation} demand for downside protection)")
    else:
        print("IV Skew: Not available")
    
    # Put-call ratio indicates market sentiment
    if options_data["put_call_ratio"] is not None:
        ratio = options_data["put_call_ratio"]
        sentiment = "bearish" if ratio > 1 else "neutral" if ratio > 0.7 else "bullish"
        print(f"Put-Call Ratio: {ratio:.2f} ({sentiment} sentiment)")
    else:
        print("Put-Call Ratio: Not available")
    
    # Open interest indicates liquidity
    if options_data["open_interest_total"] is not None:
        print(f"Total Open Interest: {options_data['open_interest_total']:,}")
    else:
        print("Total Open Interest: Not available")
    
    if options_data["open_interest_change"] is not None:
        change = options_data["open_interest_change"]
        direction = "increase" if change > 0 else "decrease" if change < 0 else "no change"
        print(f"Open Interest Change: {abs(change):,} ({direction})")
    else:
        print("Open Interest Change: Not available")
    
    print("=============================")

if __name__ == "__main__":
    # Example usage
    import sys
    
    if len(sys.argv) > 1:
        ticker = sys.argv[1].upper()
    else:
        ticker = "SPY"  # Default ticker
    
    print(f"Fetching options market data for {ticker}...")
    options_data = get_options_snapshot(ticker)
    print_options_summary(options_data) 