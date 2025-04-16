#!/usr/bin/env python
"""
Financial News Snapshot

This script fetches the latest financial news headlines once,
runs LLM interpretation on each, and displays them in a formatted way.
Also provides the option to save results to a file.
"""

import os
import datetime
import json
import argparse
from typing import List, Dict, Any
from rss_ingestor import fetch_rss_headlines, FINANCIAL_FEEDS
from llm_event_classifier import classify_macro_event
from colorama import init, Fore, Style

# Initialize colorama for cross-platform colored terminal output
init()

# Configuration
MAX_HEADLINES = 10  # Number of headlines to display

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

def interpret_headline(headline: Dict[str, Any]) -> Dict[str, Any]:
    """Use LLM to interpret a headline."""
    try:
        classification = classify_macro_event(headline)
        
        # Add the classification to the headline
        headline_with_classification = headline.copy()
        headline_with_classification.update(classification)
        return headline_with_classification
    except Exception as e:
        print(f"{Fore.RED}Error interpreting headline: {str(e)}{Style.RESET_ALL}")
        return headline

def save_to_json(headlines: List[Dict[str, Any]], filename: str) -> None:
    """Save headlines with LLM analysis to a JSON file."""
    try:
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(headlines, f, indent=2)
            
        print(f"{Fore.GREEN}Successfully saved {len(headlines)} headlines to {filename}{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Error saving JSON file: {str(e)}{Style.RESET_ALL}")

def save_to_text(headlines: List[Dict[str, Any]], filename: str) -> None:
    """Save headlines with LLM analysis to a plain text file."""
    try:
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        with open(filename, 'w', encoding='utf-8') as f:
            # Write header
            f.write("========== FINANCIAL NEWS SNAPSHOT ==========\n")
            f.write(f"Showing {len(headlines)} headlines from {len(FINANCIAL_FEEDS)} news sources\n")
            f.write(f"Generated at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("============================================\n\n")
            
            # Write news sources
            f.write("News Sources:\n")
            for i, feed in enumerate(FINANCIAL_FEEDS, 1):
                f.write(f"  {i}. {feed['source']}\n")
            f.write("\n")
            
            # Write headlines
            f.write("Latest Headlines:\n")
            
            for i, headline in enumerate(headlines, 1):
                time_str = headline.get('published', '')
                source = headline.get('source', 'Unknown')
                
                # Write headline
                f.write(f"{i}. {headline['title']}\n")
                f.write(f"   {time_str} | {source}\n")
                
                # Write LLM analysis
                event_type = headline.get('event_type')
                sentiment = headline.get('sentiment')
                sector = headline.get('sector')
                
                if event_type or sentiment or sector:
                    f.write(f"   LLM Analysis: ")
                    
                    if event_type:
                        f.write(f"{event_type}")
                        if sentiment or sector:
                            f.write(" | ")
                    
                    if sentiment:
                        f.write(f"{sentiment}")
                        if sector:
                            f.write(" | ")
                    
                    if sector:
                        f.write(f"{sector}")
                    
                    f.write("\n")
                else:
                    f.write("   No LLM analysis available\n")
                
                # Add link
                if headline.get('link'):
                    f.write(f"   URL: {headline['link']}\n")
                
                f.write("\n")  # Empty line between headlines
                
        print(f"{Fore.GREEN}Successfully saved {len(headlines)} headlines to {filename}{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Error saving text file: {str(e)}{Style.RESET_ALL}")

def main():
    """Fetch headlines, run interpretation, and display them."""
    # Set up command line arguments
    parser = argparse.ArgumentParser(description='Financial News Snapshot with LLM Analysis')
    parser.add_argument('--save', action='store_true', help='Save results to files')
    parser.add_argument('--count', type=int, default=MAX_HEADLINES, help=f'Number of headlines to display (default: {MAX_HEADLINES})')
    parser.add_argument('--output-dir', type=str, default='news_data', help='Directory to save output files (default: news_data)')
    args = parser.parse_args()
    
    # Update MAX_HEADLINES if provided
    max_count = args.count
    
    print(f"{Fore.YELLOW}Fetching financial news headlines...{Style.RESET_ALL}")
    
    # Fetch headlines
    all_headlines = fetch_rss_headlines()
    
    if not all_headlines:
        print(f"{Fore.RED}No headlines found. Check your internet connection or RSS feeds.{Style.RESET_ALL}")
        return
    
    # Sort by published date (newest first)
    all_headlines.sort(key=lambda h: h.get('published', ''), reverse=True)
    
    # Take only the most recent headlines
    latest_headlines = all_headlines[:max_count]
    
    # Print header
    print(f"{Fore.CYAN}========== FINANCIAL NEWS SNAPSHOT =========={Style.RESET_ALL}")
    print(f"Showing {len(latest_headlines)} headlines from {len(FINANCIAL_FEEDS)} news sources")
    print(f"Generated at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{Fore.CYAN}============================================{Style.RESET_ALL}\n")
    
    # Print news sources
    print(f"{Fore.YELLOW}News Sources:{Style.RESET_ALL}")
    for i, feed in enumerate(FINANCIAL_FEEDS, 1):
        print(f"  {i}. {feed['source']}")
    print()
    
    # Process and display headlines
    print(f"{Fore.YELLOW}Latest Headlines:{Style.RESET_ALL}")
    
    interpreted_headlines = []
    
    for i, headline in enumerate(latest_headlines, 1):
        time_ago = format_time_ago(headline.get('published', ''))
        source = headline.get('source', 'Unknown')
        
        # Print headline with number, time, and source
        print(f"{Fore.GREEN}{i}.{Style.RESET_ALL} {headline['title']}")
        print(f"   {Fore.BLUE}{time_ago} | {source}{Style.RESET_ALL}")
        
        # Interpret headline with LLM
        print(f"   {Fore.MAGENTA}Analyzing with LLM...{Style.RESET_ALL}")
        interpreted = interpret_headline(headline)
        interpreted_headlines.append(interpreted)
        
        # Display interpretation
        event_type = interpreted.get('event_type')
        sentiment = interpreted.get('sentiment')
        sector = interpreted.get('sector')
        
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
        else:
            print(f"   {Fore.RED}No LLM analysis available{Style.RESET_ALL}")
        
        print()  # Empty line between headlines
    
    # Save results if requested
    if args.save:
        # Generate timestamp for filenames
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create output directory
        output_dir = args.output_dir
        
        # Save as JSON
        json_filename = os.path.join(output_dir, f"news_snapshot_{timestamp}.json")
        save_to_json(interpreted_headlines, json_filename)
        
        # Save as text
        text_filename = os.path.join(output_dir, f"news_snapshot_{timestamp}.txt")
        save_to_text(interpreted_headlines, text_filename)

if __name__ == "__main__":
    main() 