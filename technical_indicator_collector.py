#!/usr/bin/env python
"""
TECHNICAL INDICATOR COLLECTOR
============================

What This Module Does:
--------------------
This module calculates key technical indicators for a given stock ticker
as of a specific date. It provides functions to retrieve RSI, MACD, and moving
average crossover signals.

How to Use:
----------
1. Import the module:
   from technical_indicator_collector import get_technical_indicators

2. Get technical indicators for a specific ticker and date:
   indicators = get_technical_indicators("AAPL", "2023-12-31")
   
3. Access specific indicators:
   rsi = indicators["rsi"]
   macd_cross = indicators["macd_cross"]
   
What This Helps You See:
-----------------------
- Momentum indicators (RSI, MACD) to gauge overbought/oversold conditions
- Trend indicators (SMA/EMA crossovers) to identify bullish/bearish shifts
- Technical signals that can complement fundamental and macro analysis
"""

import yfinance as yf
import pandas as pd
import numpy as np
import datetime
from typing import Dict, Any, Optional
import warnings

def get_technical_indicators(ticker: str, date: Optional[str] = None) -> Dict[str, Any]:
    """
    Calculate technical indicators for a given ticker as of the specified date.
    
    Args:
        ticker: Stock ticker symbol
        date: Date string in YYYY-MM-DD format (defaults to today if None)
        
    Returns:
        Dictionary containing technical indicators:
        {
            "rsi": 14-day RSI value (0-100),
            "macd_cross": MACD signal line crossover status ("bullish", "bearish", or "neutral"),
            "sma_50": 50-day Simple Moving Average,
            "sma_200": 200-day Simple Moving Average,
            "trend_cross": Moving average crossover status ("golden_cross", "death_cross", or "none"),
            "last_close": Last closing price
        }
    """
    # Set default date to today if not provided
    if date is None:
        date = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # Ensure date is in the correct format
    try:
        end_date = pd.to_datetime(date)
        # Add one day to include the end date in the data
        end_date_plus = end_date + pd.Timedelta(days=1)
        end_date_str = end_date_plus.strftime("%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Invalid date format: {date}. Expected format: YYYY-MM-DD")
    
    # Calculate start date (90 days before end date to have enough data for indicators)
    # We need at least 200 days for the 200-day moving average
    start_date = end_date - pd.Timedelta(days=250)
    start_date_str = start_date.strftime("%Y-%m-%d")
    
    try:
        # Fetch historical data
        df = yf.download(ticker, start=start_date_str, end=end_date_str, progress=False)
        
        # Check if we have enough data
        if len(df) < 200:
            warnings.warn(f"Insufficient data for {ticker}. Got {len(df)} days, need at least 200 for complete indicators.")
        
        # Calculate RSI
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        # Calculate average gain and loss
        avg_gain = gain.rolling(window=14).mean()
        avg_loss = loss.rolling(window=14).mean()
        
        # Calculate RS and RSI
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        # Calculate MACD
        ema_12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema_26 = df['Close'].ewm(span=26, adjust=False).mean()
        macd = ema_12 - ema_26
        signal = macd.ewm(span=9, adjust=False).mean()
        
        # Determine MACD crossover
        if len(macd) >= 2 and len(signal) >= 2:
            macd_cross = 'bullish' if macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-2] < signal.iloc[-2] else \
                         'bearish' if macd.iloc[-1] < signal.iloc[-1] and macd.iloc[-2] > signal.iloc[-2] else \
                         'neutral'
        else:
            macd_cross = 'neutral'
        
        # Calculate SMAs
        sma_50 = df['Close'].rolling(window=50).mean()
        sma_200 = df['Close'].rolling(window=200).mean()
        
        # Determine SMA crossover
        if len(sma_50) >= 2 and len(sma_200) >= 2:
            cross_type = 'golden_cross' if sma_50.iloc[-1] > sma_200.iloc[-1] and sma_50.iloc[-2] < sma_200.iloc[-2] else \
                         'death_cross' if sma_50.iloc[-1] < sma_200.iloc[-1] and sma_50.iloc[-2] > sma_200.iloc[-2] else \
                         'none'
        else:
            cross_type = 'none'
        
        # Determine overall trend
        if len(sma_50) > 0 and len(sma_200) > 0:
            trend = 'bullish' if sma_50.iloc[-1] > sma_200.iloc[-1] else 'bearish'
        else:
            trend = 'unknown'
        
        # Get last closing price
        last_close = df['Close'].iloc[-1] if len(df) > 0 else None
        
        # Return the indicators
        return {
            "rsi": round(rsi.iloc[-1], 2) if not pd.isna(rsi.iloc[-1]) else None,
            "macd_cross": macd_cross,
            "sma_50": round(sma_50.iloc[-1], 2) if not pd.isna(sma_50.iloc[-1]) else None,
            "sma_200": round(sma_200.iloc[-1], 2) if not pd.isna(sma_200.iloc[-1]) else None,
            "trend_cross": cross_type,
            "trend": trend,
            "last_close": round(last_close, 2) if last_close is not None else None,
            "_calculation_date": end_date.strftime("%Y-%m-%d")
        }
    
    except Exception as e:
        warnings.warn(f"Error calculating technical indicators for {ticker}: {str(e)}")
        return {
            "rsi": None,
            "macd_cross": "unknown",
            "sma_50": None,
            "sma_200": None,
            "trend_cross": "unknown",
            "trend": "unknown",
            "last_close": None,
            "_calculation_date": end_date.strftime("%Y-%m-%d"),
            "_error": str(e)
        }

def print_technical_summary(indicators: Dict[str, Any]) -> None:
    """
    Print a human-readable summary of technical indicators.
    
    Args:
        indicators: Dictionary of technical indicators from get_technical_indicators
    """
    print("\n=== TECHNICAL INDICATORS ===")
    
    # Print RSI with interpretation
    rsi = indicators.get("rsi")
    if rsi is not None:
        rsi_interp = "OVERBOUGHT" if rsi > 70 else "OVERSOLD" if rsi < 30 else "NEUTRAL"
        print(f"RSI (14): {rsi:.2f} - {rsi_interp}")
    else:
        print("RSI: Not available")
    
    # Print MACD crossover
    macd_cross = indicators.get("macd_cross")
    if macd_cross != "unknown":
        macd_signal = "BUY SIGNAL" if macd_cross == "bullish" else "SELL SIGNAL" if macd_cross == "bearish" else "NO SIGNAL"
        print(f"MACD Cross: {macd_cross.upper()} - {macd_signal}")
    else:
        print("MACD Cross: Not available")
    
    # Print moving averages
    sma_50 = indicators.get("sma_50")
    sma_200 = indicators.get("sma_200")
    if sma_50 is not None and sma_200 is not None:
        print(f"50-day SMA: {sma_50:.2f}")
        print(f"200-day SMA: {sma_200:.2f}")
        
        # Print MA relation
        relation = "ABOVE" if sma_50 > sma_200 else "BELOW"
        print(f"50-day SMA is {relation} 200-day SMA")
    else:
        print("Moving Averages: Not available")
    
    # Print crossover event if it just happened
    cross_type = indicators.get("trend_cross")
    if cross_type and cross_type != "none" and cross_type != "unknown":
        cross_signal = "BULLISH" if cross_type == "golden_cross" else "BEARISH"
        print(f"RECENT CROSSOVER: {cross_type.upper()} - {cross_signal}")
    
    # Print last close
    last_close = indicators.get("last_close")
    if last_close is not None:
        print(f"Last Close: ${last_close:.2f}")
    
    print("=============================")

if __name__ == "__main__":
    import sys
    
    # Get ticker from command line or use default
    ticker = sys.argv[1] if len(sys.argv) > 1 else "SPY"
    
    # Get date from command line or use default (today)
    date = sys.argv[2] if len(sys.argv) > 2 else None
    
    print(f"Calculating technical indicators for {ticker} as of {date or 'today'}...")
    indicators = get_technical_indicators(ticker, date)
    print_technical_summary(indicators) 