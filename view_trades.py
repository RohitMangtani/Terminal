#!/usr/bin/env python
"""
Utility script to view and manage saved trade recommendations.
"""

import os
import sys
import json
import argparse
from typing import List, Dict, Any
from datetime import datetime
from trade_persistence import load_existing_trades, TRADES_DIR, DEFAULT_TRADES_FILE

def format_trade(trade: Dict[str, Any]) -> str:
    """
    Format a trade record for display.
    
    Args:
        trade: Trade record dictionary
        
    Returns:
        Formatted string representation
    """
    try:
        # Format timestamp
        timestamp = trade.get('timestamp', 'Unknown')
        try:
            dt = datetime.fromisoformat(timestamp)
            timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            pass
        
        # Get headline info
        headline = trade.get('headline', {})
        title = headline.get('title', 'Unknown headline')
        event_type = headline.get('event_type', 'Unknown')
        sentiment = headline.get('sentiment', 'Unknown')
        sector = headline.get('sector', 'Unknown')
        
        # Get trade idea
        trade_idea = trade.get('trade_idea', {})
        ticker = trade_idea.get('ticker', 'Unknown')
        option_type = trade_idea.get('option_type', 'Unknown')
        strike = trade_idea.get('strike', 'Unknown')
        expiry = trade_idea.get('expiry', 'Unknown')
        rationale = trade_idea.get('rationale', 'No rationale provided')
        
        # Format and return
        return f"""
Trade from {timestamp}:
Headline: {title}
Classification: {event_type} | {sentiment} | {sector}
Trade: {option_type} {ticker} {strike} {expiry}
Rationale: {rationale}
"""
    except Exception as e:
        return f"Error formatting trade: {str(e)}"

def view_trades(
    count: int = None, 
    ticker: str = None, 
    option_type: str = None,
    event_type: str = None,
    sentiment: str = None,
    sector: str = None
) -> None:
    """
    View saved trades with optional filtering.
    
    Args:
        count: Maximum number of trades to display
        ticker: Filter by ticker symbol
        option_type: Filter by option type (CALL/PUT)
        event_type: Filter by event type
        sentiment: Filter by sentiment
        sector: Filter by sector
    """
    # Load trades
    trades = load_existing_trades()
    
    if not trades:
        print("No trades found in storage.")
        return
    
    # Apply filters
    filtered_trades = trades
    
    if ticker:
        filtered_trades = [
            t for t in filtered_trades 
            if t.get('trade_idea', {}).get('ticker', '').upper() == ticker.upper()
        ]
    
    if option_type:
        filtered_trades = [
            t for t in filtered_trades 
            if t.get('trade_idea', {}).get('option_type', '').upper() == option_type.upper()
        ]
    
    if event_type:
        filtered_trades = [
            t for t in filtered_trades 
            if t.get('headline', {}).get('event_type', '').upper() == event_type.upper()
        ]
    
    if sentiment:
        filtered_trades = [
            t for t in filtered_trades 
            if t.get('headline', {}).get('sentiment', '').upper() == sentiment.upper()
        ]
    
    if sector:
        filtered_trades = [
            t for t in filtered_trades 
            if t.get('headline', {}).get('sector', '').upper() == sector.upper()
        ]
    
    # Limit count
    if count is not None:
        filtered_trades = filtered_trades[:count]
    
    # Display results
    if not filtered_trades:
        print("No trades match the specified filters.")
        return
    
    print(f"Found {len(filtered_trades)} trade(s):")
    for i, trade in enumerate(filtered_trades):
        print(f"Trade {i+1}:" + format_trade(trade))
        print("-" * 80)

def show_trade_statistics() -> None:
    """Show statistics about saved trades."""
    trades = load_existing_trades()
    
    if not trades:
        print("No trades found in storage.")
        return
    
    # Count by various dimensions
    ticker_counts = {}
    option_type_counts = {}
    event_type_counts = {}
    sentiment_counts = {}
    sector_counts = {}
    
    for trade in trades:
        # Ticker counts
        ticker = trade.get('trade_idea', {}).get('ticker', 'Unknown')
        ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1
        
        # Option type counts
        option_type = trade.get('trade_idea', {}).get('option_type', 'Unknown')
        option_type_counts[option_type] = option_type_counts.get(option_type, 0) + 1
        
        # Event type counts
        event_type = trade.get('headline', {}).get('event_type', 'Unknown')
        event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1
        
        # Sentiment counts
        sentiment = trade.get('headline', {}).get('sentiment', 'Unknown')
        sentiment_counts[sentiment] = sentiment_counts.get(sentiment, 0) + 1
        
        # Sector counts
        sector = trade.get('headline', {}).get('sector', 'Unknown')
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
    
    # Print statistics
    print(f"Total trades: {len(trades)}")
    
    print("\nTickers:")
    for ticker, count in sorted(ticker_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {ticker}: {count}")
    
    print("\nOption Types:")
    for option_type, count in sorted(option_type_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {option_type}: {count}")
    
    print("\nEvent Types:")
    for event_type, count in sorted(event_type_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {event_type}: {count}")
    
    print("\nSentiments:")
    for sentiment, count in sorted(sentiment_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {sentiment}: {count}")
    
    print("\nSectors:")
    for sector, count in sorted(sector_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {sector}: {count}")

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="View and manage saved trade recommendations.")
    
    # Command subparsers
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # View command
    view_parser = subparsers.add_parser("view", help="View saved trades")
    view_parser.add_argument("--count", "-n", type=int, help="Maximum number of trades to display")
    view_parser.add_argument("--ticker", "-t", help="Filter by ticker symbol")
    view_parser.add_argument("--option", "-o", help="Filter by option type (CALL/PUT)")
    view_parser.add_argument("--event", "-e", help="Filter by event type")
    view_parser.add_argument("--sentiment", "-s", help="Filter by sentiment")
    view_parser.add_argument("--sector", "-c", help="Filter by sector")
    
    # Stats command
    subparsers.add_parser("stats", help="Show statistics about saved trades")
    
    # Parse arguments
    args = parser.parse_args()
    
    # Default to view command if none specified
    if not args.command:
        args.command = "view"
    
    # Execute command
    if args.command == "view":
        view_trades(
            count=args.count,
            ticker=args.ticker,
            option_type=args.option,
            event_type=args.event,
            sentiment=args.sentiment,
            sector=args.sector
        )
    elif args.command == "stats":
        show_trade_statistics()
    else:
        parser.print_help()

if __name__ == "__main__":
    main() 