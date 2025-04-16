#!/usr/bin/env python
"""
Real-time Financial News Monitor and Trading Opportunity Scanner

This script continuously monitors financial news feeds, classifies headlines,
and identifies potential trading opportunities across multiple time frames.
It prioritizes events based on market impact and filters for the most actionable trades.
"""

import time
import os
import datetime
from typing import List, Dict, Any, Set, Optional, Tuple
from rss_ingestor import fetch_rss_headlines, FINANCIAL_FEEDS
from llm_event_classifier import classify_macro_event
from macro_data_collector import get_macro_snapshot
from trade_picker import generate_trade_idea
from historical_matcher import match_event
from logger import get_logger
from colorama import init, Fore, Style
import threading
import signal
import sys
import json

# Initialize colorama for cross-platform colored terminal output
init()

# Initialize logger
logger = get_logger(__name__)

# Configuration
MAX_HEADLINES = 25  # Number of headlines to track at once
REFRESH_INTERVAL = 300  # Check for new headlines every X seconds (5 min)
AUTO_INTERPRET = True  # Automatically run LLM interpretation for new headlines
OPPORTUNITY_SCAN_INTERVAL = 1800  # Scan for opportunities every X seconds (30 min)
TIME_FRAMES = ["short", "medium", "long"]  # Trading time frames to scan for
PRIORITY_THRESHOLDS = {
    "high": 0.8,   # High priority match score threshold
    "medium": 0.6, # Medium priority match score threshold
    "low": 0.4     # Low priority match score threshold
}
MAX_OPPORTUNITIES = 5  # Maximum opportunities to track per time frame

# Global state
seen_headlines = set()  # Track headlines we've already seen
latest_headlines = []  # Store the latest headlines
trading_opportunities = {
    "short": [],  # Short-term opportunities (days)
    "medium": [], # Medium-term opportunities (weeks)
    "long": []    # Long-term opportunities (months)
}
opportunity_lock = threading.Lock()  # Lock for updating opportunities
running = True  # Control the main loop
interpret_lock = threading.Lock()  # Lock for interpreting headlines

def clear_screen():
    """Clear the terminal screen in a cross-platform way."""
    os.system('cls' if os.name == 'nt' else 'clear')

def format_time_ago(timestamp_str: str) -> str:
    """Convert ISO timestamp to a human-readable 'X minutes ago' format."""
    try:
        timestamp = datetime.datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%SZ")
        timestamp = timestamp.replace(tzinfo=datetime.timezone.utc)
        now = datetime.datetime.now(datetime.timezone.utc)
        
        delta = now - timestamp
        
        if delta.days > 0:
            return f"{delta.days}d ago"
        elif delta.seconds >= 3600:
            hours = delta.seconds // 3600
            return f"{hours}h ago"
        elif delta.seconds >= 60:
            minutes = delta.seconds // 60
            return f"{minutes}m ago"
        else:
            return "just now"
    except Exception:
        return "unknown time"

def get_headline_key(headline: Dict[str, Any]) -> str:
    """Create a unique key for a headline to detect duplicates."""
    return f"{headline['title']}|{headline['source']}"

def fetch_latest_headlines() -> List[Dict[str, Any]]:
    """Fetch the latest headlines and update the seen set."""
    global seen_headlines, latest_headlines
    
    try:
        all_headlines = fetch_rss_headlines()
        
        # Sort by published date (newest first)
        all_headlines.sort(key=lambda h: h.get('published', ''), reverse=True)
        
        # Filter out headlines we've already seen
        new_headlines = []
        for headline in all_headlines:
            key = get_headline_key(headline)
            if key not in seen_headlines:
                seen_headlines.add(key)
                new_headlines.append(headline)
        
        # Update our latest headlines (keeping only MAX_HEADLINES)
        latest_headlines = (new_headlines + latest_headlines)[:MAX_HEADLINES]
        
        return new_headlines
    except Exception as e:
        error_msg = f"Error fetching headlines: {str(e)}"
        print(f"{Fore.RED}{error_msg}{Style.RESET_ALL}")
        logger.error(error_msg)
        return []

def interpret_headline(headline: Dict[str, Any]) -> Dict[str, Any]:
    """Use LLM to interpret a headline and add event classification."""
    try:
        with interpret_lock:
            logger.info(f"Interpreting headline: {headline.get('title', 'Unknown')}")
            classification = classify_macro_event(headline)
            
            # Add the classification to the headline
            headline_with_classification = headline.copy()
            headline_with_classification.update(classification)
            logger.info(f"Classified as: {classification.get('event_type', 'Unknown')} / {classification.get('sentiment', 'Unknown')}")
            return headline_with_classification
    except Exception as e:
        error_msg = f"Error interpreting headline: {str(e)}"
        print(f"{Fore.RED}{error_msg}{Style.RESET_ALL}")
        logger.error(error_msg)
        return headline

def find_historical_matches(headline: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Find historical matches for a headline."""
    try:
        # Check if headline has required classification data
        if not all(k in headline for k in ['event_type', 'sentiment', 'sector']):
            logger.warning(f"Headline missing classification data: {headline.get('title', 'Unknown')}")
            return []
        
        logger.info(f"Finding historical matches for: {headline.get('title', 'Unknown')}")
        matches = match_event(headline)
        logger.info(f"Found {len(matches)} historical matches")
        return matches
    except Exception as e:
        error_msg = f"Error finding historical matches: {str(e)}"
        logger.error(error_msg)
        return []

def generate_trade_opportunity(headline: Dict[str, Any], matches: List[Dict[str, Any]], time_frame: str) -> Optional[Dict[str, Any]]:
    """Generate a trade opportunity for a specific time frame."""
    try:
        if not matches:
            return None
            
        logger.info(f"Generating {time_frame}-term trade for: {headline.get('title', 'Unknown')}")
        
        # Get macro context for trade generation
        macro_context = get_macro_snapshot(use_cache=True)
        
        # Adjust expiration parameters based on time frame
        trade_params = {}
        if time_frame == "short":
            trade_params = {"min_days": 1, "max_days": 14}  # 1 day to 2 weeks
        elif time_frame == "medium":
            trade_params = {"min_days": 15, "max_days": 45}  # 2 weeks to 6 weeks
        elif time_frame == "long":
            trade_params = {"min_days": 45, "max_days": 120}  # 6 weeks to 4 months
        
        # Generate trade idea with time frame parameters
        trade = generate_trade_idea(headline, matches)
        
        # Skip if no valid trade was generated
        if not trade or not trade.get('ticker') or not trade.get('option_type'):
            return None
            
        # Calculate priority based on match scores and event significance
        top_match = max(matches, key=lambda m: m.get('match_score', 0))
        match_score = top_match.get('match_score', 0)
        price_change = abs(top_match.get('price_change_pct', 0))
        
        # More significant price changes get higher priority
        priority = "low"
        if match_score >= PRIORITY_THRESHOLDS["high"] and price_change > 5.0:
            priority = "high"
        elif match_score >= PRIORITY_THRESHOLDS["medium"] and price_change > 2.5:
            priority = "medium"
        
        # Create opportunity object
        opportunity = {
            "headline": headline.get('title', 'Unknown'),
            "event_type": headline.get('event_type', 'Unknown'),
            "sentiment": headline.get('sentiment', 'Unknown'),
            "sector": headline.get('sector', 'Unknown'),
            "time_frame": time_frame,
            "priority": priority,
            "match_score": match_score,
            "expected_move": f"{price_change:.2f}%",
            "trade": trade,
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        logger.info(f"Generated {priority} priority {time_frame}-term trade for {trade.get('ticker', 'Unknown')}")
        return opportunity
    
    except Exception as e:
        error_msg = f"Error generating trade opportunity: {str(e)}"
        logger.error(error_msg)
        return None

def scan_for_opportunities():
    """Scan headlines for new trading opportunities."""
    global trading_opportunities
    
    try:
        logger.info("Starting opportunity scan")
        # Process only headlines with classification data
        classified_headlines = [h for h in latest_headlines if 'event_type' in h and 'sentiment' in h]
        
        if not classified_headlines:
            logger.info("No classified headlines available for opportunity scan")
            return
            
        logger.info(f"Scanning {len(classified_headlines)} headlines for opportunities")
        
        new_opportunities = {time_frame: [] for time_frame in TIME_FRAMES}
        
        for headline in classified_headlines:
            # Find historical matches
            matches = find_historical_matches(headline)
            
            if not matches:
                continue
                
            # Generate opportunities for each time frame
            for time_frame in TIME_FRAMES:
                opportunity = generate_trade_opportunity(headline, matches, time_frame)
                if opportunity:
                    new_opportunities[time_frame].append(opportunity)
        
        # Update the global trading opportunities
        with opportunity_lock:
            for time_frame in TIME_FRAMES:
                # Sort new opportunities by priority and match score
                sorted_opportunities = sorted(
                    new_opportunities[time_frame],
                    key=lambda o: (
                        0 if o["priority"] == "high" else 1 if o["priority"] == "medium" else 2,
                        -float(o.get("match_score", 0))
                    )
                )
                
                # Merge with existing opportunities, keeping only the best MAX_OPPORTUNITIES
                current = trading_opportunities[time_frame]
                merged = sorted_opportunities + current
                
                # Sort again and limit to MAX_OPPORTUNITIES
                merged = sorted(
                    merged,
                    key=lambda o: (
                        0 if o["priority"] == "high" else 1 if o["priority"] == "medium" else 2,
                        -float(o.get("match_score", 0))
                    )
                )[:MAX_OPPORTUNITIES]
                
                trading_opportunities[time_frame] = merged
        
        logger.info("Opportunity scan complete")
        logger.info(f"Current opportunities: Short: {len(trading_opportunities['short'])}, Medium: {len(trading_opportunities['medium'])}, Long: {len(trading_opportunities['long'])}")
        
    except Exception as e:
        error_msg = f"Error in opportunity scan: {str(e)}"
        print(f"{Fore.RED}{error_msg}{Style.RESET_ALL}")
        logger.error(error_msg)

def display_headlines():
    """Display the current set of headlines."""
    clear_screen()
    
    # Print header
    print(f"{Fore.CYAN}========== FINANCIAL NEWS MONITOR =========={Style.RESET_ALL}")
    print(f"Monitoring {len(FINANCIAL_FEEDS)} news feeds | Refreshed at: {datetime.datetime.now().strftime('%H:%M:%S')}")
    print(f"Press Ctrl+C to exit")
    print(f"{Fore.CYAN}============================================{Style.RESET_ALL}\n")
    
    # Print news sources being monitored
    print(f"{Fore.YELLOW}News Sources:{Style.RESET_ALL}")
    for i, feed in enumerate(FINANCIAL_FEEDS, 1):
        print(f"  {i}. {feed['source']}")
    print()
    
    # Print headlines
    if not latest_headlines:
        print(f"{Fore.YELLOW}No headlines available yet. Waiting for data...{Style.RESET_ALL}")
        return
    
    print(f"{Fore.YELLOW}Latest Headlines:{Style.RESET_ALL}")
    for i, headline in enumerate(latest_headlines[:10], 1):  # Show top 10
        time_ago = format_time_ago(headline.get('published', ''))
        source = headline.get('source', 'Unknown')
        
        # Print headline with number, time, and source
        print(f"{Fore.GREEN}{i}.{Style.RESET_ALL} {headline['title']}")
        print(f"   {Fore.BLUE}{time_ago} | {source}{Style.RESET_ALL}")
        
        # If we have LLM interpretation data, show it
        event_type = headline.get('event_type')
        sentiment = headline.get('sentiment')
        sector = headline.get('sector')
        
        if event_type or sentiment or sector:
            print(f"   {Fore.MAGENTA}LLM Analysis:{Style.RESET_ALL}", end=" ")
            
            if event_type:
                print(f"{Fore.YELLOW}{event_type}{Style.RESET_ALL}", end=" | ")
            
            if sentiment:
                # Color-code the sentiment
                sentiment_color = Fore.GREEN if sentiment == "Bullish" else Fore.RED if sentiment == "Bearish" else Fore.YELLOW
                print(f"{sentiment_color}{sentiment}{Style.RESET_ALL}", end=" | ")
            
            if sector:
                print(f"{Fore.CYAN}{sector}{Style.RESET_ALL}", end="")
            
            print()  # End the line
        
        print()  # Empty line between headlines
    
    # Print trading opportunities
    print(f"\n{Fore.YELLOW}Trading Opportunities:{Style.RESET_ALL}")
    
    for time_frame in TIME_FRAMES:
        opportunities = trading_opportunities[time_frame]
        
        # Skip if no opportunities for this time frame
        if not opportunities:
            continue
        
        print(f"\n{Fore.CYAN}{time_frame.upper()}-TERM OPPORTUNITIES:{Style.RESET_ALL}")
        
        for i, opportunity in enumerate(opportunities, 1):
            # Set color based on priority
            priority_color = Fore.RED if opportunity["priority"] == "high" else Fore.YELLOW if opportunity["priority"] == "medium" else Fore.WHITE
            sentiment_color = Fore.GREEN if opportunity["sentiment"] == "Bullish" else Fore.RED if opportunity["sentiment"] == "Bearish" else Fore.YELLOW
            
            trade = opportunity["trade"]
            ticker = trade.get("ticker", "Unknown")
            option_type = trade.get("option_type", "Unknown")
            strike = trade.get("strike", "Unknown")
            expiry = trade.get("expiry", "Unknown")
            
            print(f"{priority_color}{i}. [{opportunity['priority'].upper()}] {ticker} {option_type}{Style.RESET_ALL}")
            print(f"   Event: {opportunity['headline']}")
            print(f"   Analysis: {opportunity['event_type']} | {sentiment_color}{opportunity['sentiment']}{Style.RESET_ALL} | {Fore.CYAN}{opportunity['sector']}{Style.RESET_ALL}")
            print(f"   Expected Move: {opportunity['expected_move']} | Match Score: {opportunity['match_score']:.2f}")
            print(f"   Trade: {option_type} {strike} {expiry}")
            print()

def interpret_headlines_async(headlines_to_interpret):
    """Asynchronously interpret headlines using the LLM."""
    for i, headline in enumerate(headlines_to_interpret):
        if not running:
            break
            
        # Skip headlines that already have interpretations
        if 'event_type' in headline:
            continue
            
        # Interpret headline
        try:
            interpreted = interpret_headline(headline)
            
            # Update the headline in our list with the interpretation
            for j, h in enumerate(latest_headlines):
                if get_headline_key(h) == get_headline_key(headline):
                    latest_headlines[j].update({
                        'event_type': interpreted.get('event_type', 'Unknown'),
                        'sentiment': interpreted.get('sentiment', 'Unknown'),
                        'sector': interpreted.get('sector', 'Unknown')
                    })
                    break
                    
            # Refresh display after each headline is interpreted
            display_headlines()
            
        except Exception as e:
            error_msg = f"Error interpreting headline: {str(e)}"
            print(error_msg)
            logger.error(error_msg)

def save_opportunities_to_file():
    """Save current opportunities to a JSON file for external use."""
    try:
        output_file = "trading_opportunities.json"
        with open(output_file, 'w') as f:
            json.dump(trading_opportunities, f, indent=2)
        logger.info(f"Saved trading opportunities to {output_file}")
    except Exception as e:
        logger.error(f"Error saving opportunities to file: {str(e)}")

def signal_handler(sig, frame):
    """Handle Ctrl+C to cleanly exit the program."""
    global running
    print(f"\n{Fore.YELLOW}Exiting News Monitor...{Style.RESET_ALL}")
    running = False
    
    # Save opportunities before exiting
    save_opportunities_to_file()
    sys.exit(0)

def main():
    """Main function to run the news monitor."""
    global running
    
    # Set up signal handler for clean exit
    signal.signal(signal.SIGINT, signal_handler)
    
    # Initial fetch
    print(f"{Fore.YELLOW}Fetching initial headlines...{Style.RESET_ALL}")
    initial_headlines = fetch_latest_headlines()
    display_headlines()
    
    # Start interpreter thread for initial headlines if auto-interpret is on
    if AUTO_INTERPRET and initial_headlines:
        interpreter_thread = threading.Thread(
            target=interpret_headlines_async, 
            args=(latest_headlines,)
        )
        interpreter_thread.daemon = True
        interpreter_thread.start()
    
    # Counters for scheduled events
    last_headline_update = time.time()
    last_opportunity_scan = time.time()
    
    # Main loop
    while running:
        current_time = time.time()
        
        # Check if it's time to refresh headlines
        if current_time - last_headline_update >= REFRESH_INTERVAL:
            logger.info("Fetching new headlines")
            new_headlines = fetch_latest_headlines()
            display_headlines()
            last_headline_update = current_time
            
            # Interpret new headlines if auto-interpret is on
            if AUTO_INTERPRET and new_headlines:
                interpreter_thread = threading.Thread(
                    target=interpret_headlines_async, 
                    args=(new_headlines,)
                )
                interpreter_thread.daemon = True
                interpreter_thread.start()
        
        # Check if it's time to scan for trading opportunities
        if current_time - last_opportunity_scan >= OPPORTUNITY_SCAN_INTERVAL:
            logger.info("Starting scheduled opportunity scan")
            scan_thread = threading.Thread(target=scan_for_opportunities)
            scan_thread.daemon = True
            scan_thread.start()
            last_opportunity_scan = current_time
            
            # Save opportunities after scan
            save_opportunities_to_file()
        
        # Sleep to avoid high CPU usage
        time.sleep(1)

if __name__ == "__main__":
    try:
        # Log startup
        logger.info("Starting Financial News Monitor and Trading Opportunity Scanner")
        main()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Exiting News Monitor...{Style.RESET_ALL}")
        running = False
        # Save opportunities before exiting
        save_opportunities_to_file()
        logger.info("Program terminated by user") 