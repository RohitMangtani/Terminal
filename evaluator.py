#!/usr/bin/env python
"""
TRADE EVALUATOR
==============

This module evaluates previously generated trades by checking how the underlying ticker 
actually performed in the market after the trade was created.

How to Use:
----------
1. Import the evaluator in your module:
   from evaluator import evaluate_trade

2. Evaluate a trade from trade_history.json:
   evaluation = evaluate_trade(trade)

3. Access evaluation results:
   print(f"Actual move: {evaluation['actual_move_pct']}%")
   print(f"Correct direction: {evaluation['trade_direction_correct']}")
   print(f"Notes: {evaluation['notes']}")

What This Helps You See:
-----------------------
- How accurate trade predictions were
- Real market performance after a predicted event
- Whether the recommended option type (CALL/PUT) was correct
- Performance statistics for your trading algorithm
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
import numpy as np
from logger import get_logger

# Initialize logger
logger = get_logger(__name__)

# Constants
DEFAULT_EVALUATION_DAYS = 7
MIN_MOVE_THRESHOLD = 1.0  # Minimum % move to consider significant

def parse_timestamp(timestamp: str) -> datetime:
    """
    Parse a timestamp string into a datetime object.
    Handles ISO format and other common formats.
    
    Args:
        timestamp: ISO format timestamp string
        
    Returns:
        datetime object
    """
    try:
        # Try parsing as ISO format
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        return dt
    except (ValueError, AttributeError):
        # Fallback to multiple formats
        formats = [
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d"
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(timestamp, fmt)
            except ValueError:
                continue
                
        # If all parsing attempts fail
        logger.error(f"Failed to parse timestamp: {timestamp}")
        # Return current time as fallback
        return datetime.now()

def fetch_historical_data(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Fetch historical price data for a ticker from start_date to end_date.
    
    Args:
        ticker: Stock ticker symbol
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        
    Returns:
        DataFrame with historical price data
    """
    try:
        # Standardize crypto tickers
        if ticker.upper() in ["BTC", "BITCOIN", "BTCUSD"]:
            ticker = "BTC-USD"
        elif ticker.upper() in ["ETH", "ETHEREUM", "ETHUSD"]:
            ticker = "ETH-USD"
        
        logger.info(f"Fetching data for {ticker} from {start_date} to {end_date}")
        df = yf.download(ticker, start=start_date, end=end_date, progress=False)
        
        if df.empty:
            logger.warning(f"No data found for {ticker} between {start_date} and {end_date}")
            return pd.DataFrame()
            
        return df
    except Exception as e:
        logger.error(f"Error fetching data for {ticker}: {str(e)}")
        return pd.DataFrame()

def calculate_price_movement(df: pd.DataFrame) -> Tuple[float, float, float]:
    """
    Calculate price movement percentage from a DataFrame of historical prices.
    
    Args:
        df: DataFrame with historical price data
        
    Returns:
        Tuple of (price_change_pct, max_gain_pct, max_drawdown_pct)
    """
    if df.empty or len(df) < 2:
        return 0.0, 0.0, 0.0
    
    try:
        # Extract close prices
        start_price = df['Close'].iloc[0]
        end_price = df['Close'].iloc[-1]
        
        # Calculate overall price change percentage
        price_change_pct = ((end_price / start_price) - 1.0) * 100
        
        # Calculate maximum gain
        highest_price = df['High'].max()
        max_gain_pct = ((highest_price / start_price) - 1.0) * 100
        
        # Calculate maximum drawdown
        rolling_max = df['Close'].cummax()
        drawdowns = (df['Close'] / rolling_max - 1.0) * 100
        max_drawdown_pct = drawdowns.min()
        
        return float(price_change_pct), float(max_gain_pct), float(max_drawdown_pct)
    except Exception as e:
        logger.error(f"Error calculating price movement: {str(e)}")
        return 0.0, 0.0, 0.0

def determine_direction_correctness(price_change: float, option_type: str) -> bool:
    """
    Determine if the trade direction (CALL/PUT) was correct based on actual price movement.
    
    Args:
        price_change: Actual price change percentage
        option_type: "CALL" or "PUT"
        
    Returns:
        True if direction was correct, False otherwise
    """
    # For CALL options, price should go up
    if option_type.upper() == "CALL":
        return price_change > 0
    
    # For PUT options, price should go down
    elif option_type.upper() == "PUT":
        return price_change < 0
    
    # Unknown option type
    return False

def generate_evaluation_notes(
    price_change_pct: float, 
    max_gain_pct: float, 
    max_drawdown_pct: float, 
    option_type: str, 
    direction_correct: bool
) -> str:
    """
    Generate evaluation notes based on price movement and trade direction.
    
    Args:
        price_change_pct: Price change percentage
        max_gain_pct: Maximum gain percentage
        max_drawdown_pct: Maximum drawdown percentage
        option_type: "CALL" or "PUT"
        direction_correct: Whether trade direction was correct
        
    Returns:
        String with evaluation notes
    """
    notes = []
    
    # Check trade direction
    if direction_correct:
        if abs(price_change_pct) > MIN_MOVE_THRESHOLD:
            notes.append(f"[+] {option_type} direction was correct with significant movement of {price_change_pct:.2f}%")
        else:
            notes.append(f"[+] {option_type} direction was technically correct but movement was minimal ({price_change_pct:.2f}%)")
    else:
        notes.append(f"[-] {option_type} direction was incorrect. Price moved {price_change_pct:.2f}% in opposite direction")
    
    # Add details about volatility
    if max_gain_pct > 2.0:
        notes.append(f"[UP] Significant upside: Price reached +{max_gain_pct:.2f}% above start price")
        
    if max_drawdown_pct < -2.0:
        notes.append(f"[DOWN] Significant downside: Price dropped {max_drawdown_pct:.2f}% from peak")
    
    # Return combined notes
    return " | ".join(notes)

def evaluate_trade(trade: Dict[str, Any], evaluation_days: int = DEFAULT_EVALUATION_DAYS) -> Dict[str, Any]:
    """
    Evaluate a trade by checking how the underlying ticker moved after the trade was created.
    
    Args:
        trade: Trade dictionary (as stored in trade_history.json)
        evaluation_days: Number of trading days to evaluate
        
    Returns:
        Dictionary with evaluation results including:
        - actual_move_pct: Actual percentage move in the ticker
        - max_gain_pct: Maximum gain percentage during evaluation period
        - max_drawdown_pct: Maximum drawdown percentage during evaluation period
        - trade_direction_correct: Whether the option type (CALL/PUT) was correct
        - notes: Evaluation notes
    """
    # Initialize result structure
    evaluation = {
        "actual_move_pct": 0.0,
        "max_gain_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "trade_direction_correct": False,
        "notes": "Could not evaluate trade - insufficient data"
    }
    
    try:
        # Extract trade timestamp
        timestamp = trade.get('saved_timestamp')
        if not timestamp:
            logger.warning("Trade missing timestamp, using current time")
            timestamp = datetime.now().isoformat()
            
        # Parse timestamp to datetime
        trade_date = parse_timestamp(timestamp)
        
        # Extract ticker from trade
        trade_idea = trade.get('trade_idea', {})
        ticker = trade_idea.get('ticker')
        option_type = trade_idea.get('option_type', '').upper()
        
        if not ticker:
            logger.warning("Trade missing ticker symbol, cannot evaluate")
            evaluation["notes"] = "Could not evaluate trade - missing ticker symbol"
            return evaluation
            
        if not option_type in ["CALL", "PUT"]:
            logger.warning(f"Invalid option type: {option_type}")
            evaluation["notes"] = f"Could not evaluate trade - invalid option type: {option_type}"
            return evaluation
        
        # Calculate date range for evaluation
        start_date = trade_date.strftime("%Y-%m-%d")
        end_date = (trade_date + timedelta(days=evaluation_days*2)).strftime("%Y-%m-%d")
        
        # Fetch historical data
        df = fetch_historical_data(ticker, start_date, end_date)
        
        if df.empty:
            evaluation["notes"] = f"Could not evaluate trade - no data available for {ticker}"
            return evaluation
            
        # Limit to the specified number of trading days
        if len(df) > evaluation_days:
            df = df.head(evaluation_days)
        
        # Calculate price movement
        price_change_pct, max_gain_pct, max_drawdown_pct = calculate_price_movement(df)
        
        # Determine if trade direction was correct
        direction_correct = determine_direction_correctness(price_change_pct, option_type)
        
        # Generate evaluation notes
        notes = generate_evaluation_notes(
            price_change_pct, 
            max_gain_pct, 
            max_drawdown_pct, 
            option_type, 
            direction_correct
        )
        
        # Update evaluation with results
        evaluation["actual_move_pct"] = round(price_change_pct, 2)
        evaluation["max_gain_pct"] = round(max_gain_pct, 2)
        evaluation["max_drawdown_pct"] = round(max_drawdown_pct, 2)
        evaluation["trade_direction_correct"] = direction_correct
        evaluation["notes"] = notes
        evaluation["evaluation_period"] = f"{len(df)} trading days"
        evaluation["start_date"] = start_date
        evaluation["end_date"] = df.index[-1].strftime("%Y-%m-%d")
        
        logger.info(f"Evaluated {option_type} trade for {ticker}: " +
                   f"move={price_change_pct:.2f}%, correct={direction_correct}")
        
        return evaluation
    except Exception as e:
        logger.error(f"Error evaluating trade: {str(e)}", exc_info=True)
        evaluation["notes"] = f"Error evaluating trade: {str(e)}"
        return evaluation

def evaluate_trade_history(trades: List[Dict[str, Any]], evaluation_days: int = DEFAULT_EVALUATION_DAYS) -> List[Dict[str, Any]]:
    """
    Evaluate a list of trades.
    
    Args:
        trades: List of trade dictionaries
        evaluation_days: Number of trading days to evaluate
        
    Returns:
        List of trade dictionaries with evaluation results added
    """
    evaluated_trades = []
    
    for trade in trades:
        # Create a copy of the trade to avoid modifying the original
        evaluated_trade = trade.copy()
        
        # Add evaluation results
        evaluation = evaluate_trade(trade, evaluation_days)
        evaluated_trade["evaluation"] = evaluation
        
        evaluated_trades.append(evaluated_trade)
    
    return evaluated_trades
        
def calculate_success_rate(evaluated_trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate success rate and statistics from evaluated trades.
    
    Args:
        evaluated_trades: List of evaluated trade dictionaries
        
    Returns:
        Dictionary with success metrics
    """
    total_trades = len(evaluated_trades)
    
    if total_trades == 0:
        return {
            "total_trades": 0,
            "successful_trades": 0,
            "success_rate": 0.0,
            "average_move": 0.0,
            "call_success_rate": 0.0,
            "put_success_rate": 0.0
        }
    
    # Count successful trades
    successful_trades = sum(
        1 for trade in evaluated_trades 
        if trade.get("evaluation", {}).get("trade_direction_correct", False)
    )
    
    # Calculate average movement
    actual_moves = [
        trade.get("evaluation", {}).get("actual_move_pct", 0.0)
        for trade in evaluated_trades
    ]
    average_move = sum(actual_moves) / total_trades if total_trades > 0 else 0.0
    
    # Separate CALL and PUT trades
    call_trades = [
        trade for trade in evaluated_trades 
        if trade.get("trade_idea", {}).get("option_type", "").upper() == "CALL"
    ]
    
    put_trades = [
        trade for trade in evaluated_trades 
        if trade.get("trade_idea", {}).get("option_type", "").upper() == "PUT"
    ]
    
    # Calculate success rates by type
    call_success = sum(
        1 for trade in call_trades 
        if trade.get("evaluation", {}).get("trade_direction_correct", False)
    )
    
    put_success = sum(
        1 for trade in put_trades 
        if trade.get("evaluation", {}).get("trade_direction_correct", False)
    )
    
    call_success_rate = call_success / len(call_trades) if len(call_trades) > 0 else 0.0
    put_success_rate = put_success / len(put_trades) if len(put_trades) > 0 else 0.0
    
    return {
        "total_trades": total_trades,
        "successful_trades": successful_trades,
        "success_rate": round(successful_trades / total_trades * 100, 2) if total_trades > 0 else 0.0,
        "average_move": round(average_move, 2),
        "call_trades": len(call_trades),
        "call_successful": call_success,
        "call_success_rate": round(call_success_rate * 100, 2),
        "put_trades": len(put_trades),
        "put_successful": put_success,
        "put_success_rate": round(put_success_rate * 100, 2)
    }

if __name__ == "__main__":
    # Example usage
    import json
    
    # Sample trade for testing
    sample_trade = {
        "saved_timestamp": datetime.now().isoformat(),
        "trade_idea": {
            "ticker": "AAPL",
            "option_type": "CALL",
            "strike": 180.0,
            "expiry": "2023-12-15",
            "rationale": "Test trade for evaluation"
        }
    }
    
    # Evaluate the sample trade
    evaluation = evaluate_trade(sample_trade)
    
    print("\nTrade Evaluation Results:")
    print(f"Ticker: {sample_trade['trade_idea']['ticker']}")
    print(f"Option Type: {sample_trade['trade_idea']['option_type']}")
    print(f"Actual Movement: {evaluation['actual_move_pct']}%")
    print(f"Direction Correct: {evaluation['trade_direction_correct']}")
    print(f"Notes: {evaluation['notes']}")
    
    # Try to load and evaluate trades from trade_history.json if it exists
    try:
        with open("trade_history.json", "r") as f:
            trades = json.load(f)
            
        print(f"\nEvaluating {len(trades)} trades from trade_history.json...")
        evaluated_trades = evaluate_trade_history(trades)
        
        # Calculate overall success rate
        metrics = calculate_success_rate(evaluated_trades)
        print("\nOverall Performance Metrics:")
        print(f"Total Trades: {metrics['total_trades']}")
        print(f"Success Rate: {metrics['success_rate']}%")
        print(f"Average Movement: {metrics['average_move']}%")
        print(f"CALL Success Rate: {metrics['call_success_rate']}% ({metrics['call_successful']}/{metrics['call_trades']})")
        print(f"PUT Success Rate: {metrics['put_success_rate']}% ({metrics['put_successful']}/{metrics['put_trades']})")
    except FileNotFoundError:
        print("\nNo trade_history.json file found for evaluation.") 