"""
Module for persisting trade recommendations to storage.
"""

import json
import os
import datetime
from typing import Dict, List, Any, Optional

# Constants
TRADES_DIR = "trade_history"
DEFAULT_TRADES_FILE = os.path.join(TRADES_DIR, "trade_recommendations.json")

def ensure_trade_directory() -> None:
    """Ensure the trade history directory exists."""
    if not os.path.exists(TRADES_DIR):
        os.makedirs(TRADES_DIR)
        print(f"Created trade history directory: {TRADES_DIR}")

def load_existing_trades(filename: str = DEFAULT_TRADES_FILE) -> List[Dict[str, Any]]:
    """
    Load existing trades from storage.
    
    Args:
        filename: Path to the trades JSON file
        
    Returns:
        List of trade dictionaries
    """
    ensure_trade_directory()
    
    if not os.path.exists(filename):
        return []
    
    try:
        with open(filename, 'r') as f:
            trades = json.load(f)
        return trades if isinstance(trades, list) else []
    except Exception as e:
        print(f"Error loading trades from {filename}: {str(e)}")
        return []

def save_trade(trade_data: Dict[str, Any], filename: str = DEFAULT_TRADES_FILE) -> bool:
    """
    Save a trade to the trade history.
    
    Args:
        trade_data: Dictionary containing trade details
        filename: Path to the trades JSON file
        
    Returns:
        True if successful, False otherwise
    """
    ensure_trade_directory()
    
    # Add timestamp if not present
    if 'timestamp' not in trade_data:
        trade_data['timestamp'] = datetime.datetime.now().isoformat()
    
    # Load existing trades
    existing_trades = load_existing_trades(filename)
    
    # Add new trade
    existing_trades.append(trade_data)
    
    try:
        with open(filename, 'w') as f:
            json.dump(existing_trades, indent=2, fp=f)
        return True
    except Exception as e:
        print(f"Error saving trade to {filename}: {str(e)}")
        return False

def save_trade_data(
    headline: Dict[str, Any], 
    similar_events: List[Dict[str, Any]], 
    trade_idea: Dict[str, Any],
    filename: str = DEFAULT_TRADES_FILE
) -> bool:
    """
    Save complete trade data including source headline, similar events, and generated trade.
    
    Args:
        headline: The classified news headline
        similar_events: List of similar historical events
        trade_idea: Generated trade recommendation
        filename: Path to save the trade data
        
    Returns:
        True if successful, False otherwise
    """
    # Create a complete trade record
    trade_record = {
        'timestamp': datetime.datetime.now().isoformat(),
        'headline': {
            'title': headline.get('title', ''),
            'source': headline.get('source', ''),
            'published': headline.get('published', ''),
            'event_type': headline.get('event_type', ''),
            'sentiment': headline.get('sentiment', ''),
            'sector': headline.get('sector', '')
        },
        'similar_events': [
            {
                'event_summary': event.get('event_summary', ''),
                'event_date': event.get('event_date', ''),
                'match_score': event.get('match_score', 0),
                'price_change_pct': event.get('price_change_pct', 0),
                'affected_ticker': event.get('affected_ticker', '')
            }
            for event in similar_events
        ],
        'trade_idea': {
            'ticker': trade_idea.get('ticker', ''),
            'option_type': trade_idea.get('option_type', ''),
            'strike': trade_idea.get('strike', ''),
            'expiry': trade_idea.get('expiry', ''),
            'rationale': trade_idea.get('rationale', '')
        }
    }
    
    return save_trade(trade_record, filename)

if __name__ == "__main__":
    # Test the functionality
    test_trade = {
        'ticker': 'SPY',
        'option_type': 'PUT',
        'strike': 440,
        'expiry': '2023-12-15',
        'rationale': 'Test trade for demonstration'
    }
    
    if save_trade(test_trade):
        print("Successfully saved test trade.")
        
    trades = load_existing_trades()
    print(f"Loaded {len(trades)} trades from storage.") 