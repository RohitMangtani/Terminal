import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import math
import random
from pandas.tseries.offsets import BDay

def get_next_friday(from_date: datetime) -> datetime:
    """
    Get the next Friday from a given date.
    
    Args:
        from_date: Starting date
        
    Returns:
        datetime: Next Friday
    """
    days_ahead = 4 - from_date.weekday()  # Friday is 4
    if days_ahead <= 0:  # If today is Friday or weekend
        days_ahead += 7
    return from_date + timedelta(days=days_ahead)

def fetch_current_price(ticker: str) -> float:
    """
    Fetch the current price of a ticker.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        float: Current price
    """
    try:
        stock = yf.Ticker(ticker)
        price = stock.info.get('regularMarketPrice')
        
        # If price is None, try to get the last closing price
        if price is None:
            hist = stock.history(period="1d")
            if not hist.empty:
                price = hist['Close'].iloc[-1]
            else:
                return 0.0
                
        return float(price)
    except Exception as e:
        print(f"Error fetching current price for {ticker}: {str(e)}")
        return 0.0

def fetch_option_data(ticker: str) -> Tuple[List[str], pd.DataFrame]:
    """
    Fetch options data for a ticker.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        Tuple[List[str], pd.DataFrame]: List of expiry dates and options chain dataframe
    """
    try:
        stock = yf.Ticker(ticker)
        expiry_dates = stock.options
        
        if not expiry_dates:
            return [], pd.DataFrame()
            
        # Get options for the nearest expiry date
        nearest_expiry = expiry_dates[0]
        options = stock.option_chain(nearest_expiry)
        
        # Return both calls and puts
        return expiry_dates, pd.concat([options.calls, options.puts])
    except Exception as e:
        print(f"Error fetching options data for {ticker}: {str(e)}")
        return [], pd.DataFrame()

def select_expiry_date(expiry_dates: List[str], min_days: int = 7, max_days: int = 30) -> str:
    """
    Select an appropriate expiry date.
    
    Args:
        expiry_dates: List of available expiry dates
        min_days: Minimum days to expiry
        max_days: Maximum days to expiry
        
    Returns:
        str: Selected expiry date
    """
    if not expiry_dates:
        # If no expiries available, use next Friday
        next_friday = get_next_friday(datetime.now()).strftime("%Y-%m-%d")
        return next_friday
    
    today = datetime.now().date()
    
    # Filter expiry dates within desired range
    valid_expiries = []
    for expiry in expiry_dates:
        expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date()
        days_to_expiry = (expiry_date - today).days
        
        if min_days <= days_to_expiry <= max_days:
            valid_expiries.append((expiry, days_to_expiry))
    
    if valid_expiries:
        # Sort by days to expiry (ascending)
        valid_expiries.sort(key=lambda x: x[1])
        return valid_expiries[0][0]
    
    # If no dates in range, return earliest available
    return expiry_dates[0]

def select_strike_price(current_price: float, option_type: str, price_change_pct: float) -> float:
    """
    Select an appropriate strike price.
    
    Args:
        current_price: Current price of the stock
        option_type: "CALL" or "PUT"
        price_change_pct: Historical percentage price change
        
    Returns:
        float: Selected strike price
    """
    # Calculate how far OTM to go based on the size of historical move
    otm_pct = min(abs(price_change_pct) * 0.3, 5.0)  # Cap at 5%
    
    if option_type == "PUT":
        # For puts, go below current price
        target = current_price * (1 - otm_pct/100)
    else:
        # For calls, go above current price
        target = current_price * (1 + otm_pct/100)
    
    # Round to nearest 0.5 for stocks < $100, nearest 1 for stocks > $100
    if current_price < 100:
        return round(target * 2) / 2
    else:
        return round(target)

def generate_trade_idea(classified_headline: Dict[str, Any], historical_matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate a trade idea based on a classified headline and historical matches.
    
    Args:
        classified_headline: The classified news headline
        historical_matches: List of similar historical events with market impact data
        
    Returns:
        Dict[str, Any]: Trade idea with ticker, trade_type, direction, option_type, strike, expiry, and rationale
    """
    if not historical_matches:
        return {
            "ticker": None,
            "trade_type": "option",  # Default to option
            "direction": "BUY",      # Default to BUY
            "option_type": None,
            "strike": None,
            "expiry": None,
            "rationale": "No historical matches found to base trade on."
        }
    
    # Find the match with highest price change or match score as tiebreaker
    # Check for both price_change_pct and drop_pct for compatibility
    def get_price_change(event: Dict[str, Any]) -> float:
        if 'price_change_pct' in event:
            return abs(event.get('price_change_pct', 0))
        elif 'drop_pct' in event:
            return abs(event.get('drop_pct', 0))
        else:
            return 0
    
    top_match = sorted(historical_matches, key=lambda x: (get_price_change(x), x.get('match_score', 0)), reverse=True)[0]
    
    ticker = top_match.get('affected_ticker', 'SPY')
    
    # Get price change - check both possible field names for compatibility
    price_change_pct = 0
    if 'price_change_pct' in top_match:
        price_change_pct = top_match.get('price_change_pct', 0)
    elif 'drop_pct' in top_match:
        price_change_pct = top_match.get('drop_pct', 0)  # Backward compatibility
    
    # Get max drawdown percentage from the top match
    max_drawdown_pct = abs(top_match.get('max_drawdown_pct', 5.0))
    
    # Extract sentiment from the classified headline
    sentiment = classified_headline.get('sentiment', '').lower()
    
    # Extract event tags if available
    event_tags = classified_headline.get('event_tags', {})
    is_cpi_week = event_tags.get('is_cpi_week', False)
    surprise_positive = event_tags.get('surprise_positive', False)
    
    # Check for inverted yield curve in macro context if available
    inverted_curve = False
    macro_snapshot = classified_headline.get('macro_snapshot', {})
    if macro_snapshot:
        treasury2y = macro_snapshot.get('Treasury2Y')
        treasury10y = macro_snapshot.get('Treasury10Y')
        if treasury2y and treasury10y and treasury2y > treasury10y:
            inverted_curve = True
    
    # Initialize trade_type and direction
    trade_type = "option"  # Default to option
    direction = "BUY"      # Default direction for options
    
    # Check if the LLM provided a direction recommendation
    llm_direction = classified_headline.get('direction', None)
    if llm_direction and llm_direction in ["BUY", "SELL"]:
        direction = llm_direction
        # If LLM explicitly recommends SELL, consider this a strong signal
        if direction == "SELL":
            # For SELL recommendations without strong evidence, start with options
            rationale_addition = f"LLM explicitly recommends SELL direction based on the news event."
        else:
            rationale_addition = f"LLM explicitly recommends BUY direction based on the news event."
    
    # Determine option type based on price change percentage
    if price_change_pct < 0 and abs(price_change_pct) > 3.0:
        option_type = "PUT"
    else:
        option_type = "CALL"
    
    # Step 2: Implement directional logic for trade_type and direction
    # If bullish and max drawdown is low, use equity instead of options
    if sentiment == 'bullish' and max_drawdown_pct < 2.0:
        trade_type = "equity"
        # Only override direction if LLM didn't provide one or if our confidence is high
        if not llm_direction or (llm_direction != "SELL"):  # Trust our logic over LLM if it recommended SELL for bullish
            direction = "BUY"
            rationale_addition = "Using equity (BUY) due to bullish sentiment with low expected drawdown."
    
    # If bearish and we have high-risk indicators, consider equity sell
    elif sentiment == 'bearish' and (is_cpi_week or inverted_curve or surprise_positive):
        trade_type = "equity"
        # Only override direction if LLM didn't provide one or if our confidence is high
        if not llm_direction or (llm_direction != "BUY"):  # Trust our logic over LLM if it recommended BUY for bearish + risk
            direction = "SELL"
            risk_factors = []
            if is_cpi_week:
                risk_factors.append("CPI week")
            if inverted_curve:
                risk_factors.append("inverted yield curve")
            if surprise_positive:
                risk_factors.append("positive surprise in bearish context")
            rationale_addition = f"Using equity (SELL) due to bearish sentiment with risk factors: {', '.join(risk_factors)}."
    
    # Otherwise, stick with options (the default)
    else:
        # If LLM didn't provide direction or we're using options (where BUY is typical)
        if not llm_direction or trade_type == "option":
            if option_type == "PUT":
                rationale_addition = "Using PUT option due to expected significant downside move."
            else:
                rationale_addition = "Using CALL option due to expected upside potential."
    
    # Fetch current ticker price
    current_price = fetch_current_price(ticker)
    
    if current_price <= 0:
        return {
            "ticker": ticker,
            "trade_type": trade_type,
            "direction": direction,
            "option_type": option_type if trade_type == "option" else None,
            "strike": None,
            "expiry": None,
            "rationale": f"Could not fetch current price for {ticker}."
        }
    
    # Fetch option data and select strike/expiry only if this is an options trade
    selected_strike = None
    selected_expiry = None
    
    if trade_type == "option":
        # Fetch option data for the ticker
        expiry_dates, options_data = fetch_option_data(ticker)
    
        # Select expiry date
        selected_expiry = select_expiry_date(expiry_dates)
    
        # Select strike price
        selected_strike = select_strike_price(current_price, option_type, price_change_pct)
    
    # Generate rationale
    if price_change_pct < 0:
        direction_word = "drop"
    else:
        direction_word = "gain"
    
    if option_type == "PUT":
        prediction = "downside risk"
    else:
        prediction = "upside potential"
    
    # For cleaner rationale, make sure price_change_pct is displayed as a positive number
    display_pct = abs(price_change_pct)
    
    rationale = (
        f"Event similar to {top_match.get('event_summary', '')} on {top_match.get('event_date', '')}, "
        f"which caused a {display_pct:.2f}% {direction_word} in {ticker}. "
        f"Match score: {top_match.get('match_score', 0):.2f}. "
        f"Current event classified as {classified_headline.get('event_type', 'Unknown event type')}, "
        f"{classified_headline.get('sentiment', 'Unknown sentiment')}, "
        f"affecting {classified_headline.get('sector', 'Unknown sector')}. "
        f"Suggests {prediction}. {rationale_addition}"
    )
    
    return {
        "ticker": ticker,
        "trade_type": trade_type,
        "direction": direction,
        "option_type": option_type if trade_type == "option" else None,
        "strike": selected_strike,
        "expiry": selected_expiry,
        "rationale": rationale
    }

def process_headlines_for_trades(classified_headlines: List[Dict[str, Any]], historical_matches_by_headline: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    Process multiple headlines and their historical matches to generate trade ideas.
    
    Args:
        classified_headlines: List of classified headlines
        historical_matches_by_headline: List of historical matches for each headline
        
    Returns:
        List[Dict[str, Any]]: List of trade ideas
    """
    trade_ideas = []
    
    for headline, matches in zip(classified_headlines, historical_matches_by_headline):
        trade_idea = generate_trade_idea(headline, matches)
        
        # Only add valid trade ideas (for option trades, need strike price)
        if (trade_idea.get('trade_type') == 'equity' or 
            (trade_idea.get('trade_type') == 'option' and trade_idea.get('strike') is not None)):
            trade_ideas.append(trade_idea)
    
    # Sort trade ideas by priority (could implement custom logic here)
    return trade_ideas

if __name__ == "__main__":
    # Example usage with a sample headline and matches
    test_headline = {
        "title": "Fed signals potential rate cut on cooling inflation",
        "event_type": "Monetary Policy",
        "sentiment": "Bullish",
        "sector": "Financials",
        "event_tags": {
            "is_fed_week": True,
            "is_cpi_week": False,
            "surprise_positive": True
        }
    }
    
    test_matches = [
        {
            "event_summary": "Fed signals pause in rate hikes after continuous increases",
            "match_score": 0.8,
            "affected_ticker": "SPY",
            "drop_pct": 4.5,  # This is actually a gain since Fed pausing is bullish
            "max_drawdown_pct": -1.5,  # Max drawdown during the period
            "event_date": "2023-09-20"
        },
        {
            "event_summary": "Fed announces emergency rate cut during COVID-19",
            "match_score": 0.7,
            "affected_ticker": "SPY",
            "drop_pct": -2.8,  # Negative value means market dropped
            "max_drawdown_pct": -5.2,  # Max drawdown during the period
            "event_date": "2020-03-03"
        }
    ]
    
    trade_idea = generate_trade_idea(test_headline, test_matches)
    
    print("RECOMMENDED TRADE:")
    print(f"Ticker: {trade_idea['ticker']}")
    print(f"Trade Type: {trade_idea['trade_type']}")
    print(f"Direction: {trade_idea['direction']}")
    if trade_idea['trade_type'] == 'option':
        print(f"Option Type: {trade_idea['option_type']}")
        print(f"Strike: {trade_idea['strike']}")
        print(f"Expiry: {trade_idea['expiry']}")
    print(f"Rationale: {trade_idea['rationale']}") 