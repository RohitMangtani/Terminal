import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple

# Common crypto tickers and their Yahoo Finance format
CRYPTO_FORMATS = {
    "BTC": "BTC-USD",
    "BITCOIN": "BTC-USD",
    "ETH": "ETH-USD",
    "ETHEREUM": "ETH-USD",
    "XRP": "XRP-USD",
    "DOGE": "DOGE-USD",
    "DOGECOIN": "DOGE-USD",
    "ADA": "ADA-USD",
    "CARDANO": "ADA-USD"
}

def standardize_ticker(ticker: str) -> str:
    """
    Standardize ticker symbols, especially for cryptocurrencies.
    
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
    
    # Handle partial matches (e.g., "BITCOIN ETF" should match to "BTC-USD")
    for key, value in CRYPTO_FORMATS.items():
        if key in ticker:
            return value
    
    # Handle BTC/ETH formats without USD
    if ticker in ["BTC", "ETH"]:
        return f"{ticker}-USD"
    
    # If no transformations needed, return original
    return ticker

def fetch_market_data(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Fetch daily OHLC market data for a given ticker and date range.
    
    Args:
        ticker (str): The ticker symbol
        start_date (str): Start date in YYYY-MM-DD format
        end_date (str): End date in YYYY-MM-DD format
        
    Returns:
        pd.DataFrame: DataFrame with daily market data
    """
    try:
        # Standardize the ticker symbol
        original_ticker = ticker
        ticker = standardize_ticker(ticker)
        
        if original_ticker != ticker:
            print(f"Using standardized ticker: {ticker} (from {original_ticker})")
            
        # Fetch data from yfinance
        df = yf.download(ticker, start=start_date, end=end_date, progress=False)
        
        # Check if df is empty
        if df.empty:
            print(f"No data found for ticker {ticker} in specified date range")
            
            # Try SPY as fallback for market indices
            if ticker not in CRYPTO_FORMATS.values() and ticker not in ["SPY", "QQQ", "DIA"]:
                print(f"Trying SPY as a fallback for {ticker}")
                fallback_df = yf.download("SPY", start=start_date, end=end_date, progress=False)
                if not fallback_df.empty:
                    print(f"Using SPY as a fallback for {ticker}")
                    return fallback_df
            
            return pd.DataFrame()
            
        return df
    except Exception as e:
        print(f"Error fetching data for {ticker}: {str(e)}")
        return pd.DataFrame()

def calculate_price_changes(df: pd.DataFrame) -> Tuple[float, float]:
    """
    Calculate both the overall price change and maximum drawdown within the dataframe period.
    
    Args:
        df (pd.DataFrame): DataFrame with market data including 'Close' column
        
    Returns:
        Tuple[float, float]: (overall_change_pct, max_drawdown_pct)
        - overall_change_pct: Percentage change from first to last close
        - max_drawdown_pct: Maximum percentage drawdown during the period
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
            
        return float(overall_change_pct), float(max_drawdown)
    except Exception as e:
        print(f"Error calculating price change: {str(e)}")
        return 0.0, 0.0 