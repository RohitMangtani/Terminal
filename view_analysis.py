#!/usr/bin/env python
"""
View Analysis Utility

This command-line tool allows users to view and manage saved historical analyses.
"""

import os
import sys
import json
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Any
import analysis_persistence as ap

def list_analyses(ticker: str = None, days: int = 30, 
                  pattern: str = None, limit: int = 10,
                  detailed: bool = False) -> None:
    """
    List saved analyses matching the criteria
    
    Args:
        ticker: Optional ticker symbol to filter by
        days: Number of recent days to include
        pattern: Optional pattern to filter by
        limit: Maximum number of analyses to show
        detailed: Whether to show detailed information
    """
    persistence = ap.AnalysisPersistence()
    
    # Get historical event analyses
    if ticker:
        print(f"\nHistorical Event Analyses for {ticker}:")
        print("-" * 60)
        historical_analyses = persistence.find_historical_analysis(ticker=ticker)
    else:
        print("\nRecent Historical Event Analyses:")
        print("-" * 60)
        # Get all analyses and sort by saved_at (newest first)
        historical_analyses = []
        for ticker_analyses in persistence.event_index["events"].values():
            historical_analyses.extend(ticker_analyses)
    
    # Sort by saved_at (most recent first)
    historical_analyses.sort(key=lambda x: x.get("saved_at", ""), reverse=True)
    
    # Limit the number of results
    historical_analyses = historical_analyses[:limit]
    
    # Display analyses
    if historical_analyses:
        for i, analysis in enumerate(historical_analyses, 1):
            ticker = analysis.get("ticker", "Unknown")
            event_date = analysis.get("event_date", "Unknown")
            price_change = analysis.get("price_change", 0)
            trend = analysis.get("trend", "Unknown")
            saved_at = analysis.get("saved_at", "Unknown")
            file_path = analysis.get("file_path", "")
            
            print(f"{i}. {ticker} - {event_date} - {price_change}% ({trend})")
            if detailed:
                print(f"   Saved: {saved_at}")
                print(f"   File: {file_path}")
                
                # Load full analysis for detailed view
                full_analysis = persistence.load_analysis(file_path)
                if full_analysis:
                    # Show additional details
                    if "max_drawdown_pct" in full_analysis:
                        print(f"   Max Drawdown: {full_analysis.get('max_drawdown_pct')}%")
                    if "volatility_pct" in full_analysis:
                        print(f"   Volatility: {full_analysis.get('volatility_pct')}%")
                    if "days_analyzed" in full_analysis:
                        print(f"   Analysis Period: {full_analysis.get('days_analyzed')} days")
                    
                    # Show query if available
                    metadata = full_analysis.get("_metadata", {})
                    if "query" in metadata:
                        print(f"   Query: \"{metadata.get('query')}\"")
                print()
    else:
        print("No historical event analyses found.")
    
    # Get similar events analyses
    if pattern:
        print(f"\nSimilar Events Analyses matching '{pattern}':")
        print("-" * 60)
        similar_analyses = persistence.find_similar_events_analysis(pattern=pattern)
    else:
        print("\nRecent Similar Events Analyses:")
        print("-" * 60)
        # Get all analyses and sort by saved_at (newest first)
        similar_analyses = []
        for pattern_analyses in persistence.event_index["similar_events"].values():
            similar_analyses.extend(pattern_analyses)
    
    # Sort by saved_at (most recent first)
    similar_analyses.sort(key=lambda x: x.get("saved_at", ""), reverse=True)
    
    # Limit the number of results
    similar_analyses = similar_analyses[:limit]
    
    # Display analyses
    if similar_analyses:
        for i, analysis in enumerate(similar_analyses, 1):
            pattern = analysis.get("pattern", "Unknown")
            ticker = analysis.get("dominant_ticker", "Unknown")
            change = analysis.get("avg_price_change", 0)
            consistency = analysis.get("consistency_score", 0)
            saved_at = analysis.get("saved_at", "Unknown")
            file_path = analysis.get("file_path", "")
            
            print(f"{i}. {pattern} - {ticker} - {change}% (Consistency: {consistency}%)")
            if detailed:
                print(f"   Saved: {saved_at}")
                print(f"   File: {file_path}")
                
                # Load full analysis for detailed view
                full_analysis = persistence.load_analysis(file_path)
                if full_analysis:
                    # Show additional details
                    if "avg_max_drawdown" in full_analysis:
                        print(f"   Avg Max Drawdown: {full_analysis.get('avg_max_drawdown')}%")
                    if "bullish_pct" in full_analysis and "bearish_pct" in full_analysis:
                        print(f"   Trend Distribution: {full_analysis.get('bullish_pct')}% Bullish, {full_analysis.get('bearish_pct')}% Bearish")
                    if "similar_events_count" in full_analysis:
                        print(f"   Similar Events Count: {full_analysis.get('similar_events_count')}")
                    
                    # Show query if available
                    metadata = full_analysis.get("_metadata", {})
                    if "query" in metadata:
                        print(f"   Query: \"{metadata.get('query')}\"")
                print()
    else:
        print("No similar events analyses found.")

def show_analysis(file_path: str, format: str = "text") -> None:
    """
    Show a specific analysis
    
    Args:
        file_path: Path to the analysis file
        format: Output format (text or json)
    """
    persistence = ap.AnalysisPersistence()
    analysis = persistence.load_analysis(file_path)
    
    if not analysis:
        print(f"Analysis not found or could not be loaded: {file_path}")
        return
    
    if format == "json":
        # Print the raw JSON
        print(json.dumps(analysis, indent=2))
        return
    
    # Print formatted text output
    print("\n" + "=" * 80)
    
    # Determine the type of analysis
    if "price_change_pct" in analysis and "event_date" in analysis:
        # Historical event analysis
        print(f"Historical Event Analysis - {analysis.get('ticker', 'Unknown')} on {analysis.get('event_date', 'Unknown')}")
        print("-" * 80)
        
        # Event details
        print(f"Event Date: {analysis.get('event_date', 'Unknown')}")
        print(f"Ticker: {analysis.get('ticker', 'Unknown')}")
        print(f"Price Change: {analysis.get('price_change_pct', 0)}%")
        print(f"Maximum Drawdown: {analysis.get('max_drawdown_pct', 0)}%")
        print(f"Volatility: {analysis.get('volatility_pct', 0)}%")
        print(f"Trend: {analysis.get('trend', 'Unknown')}")
        print(f"Analysis Period: {analysis.get('days_analyzed', 0)} days ({analysis.get('date_range_analyzed', 'Unknown')})")
        
        # Print price details
        if all(k in analysis for k in ["start_price", "end_price", "highest_price", "lowest_price"]):
            print("\nPrice Details:")
            print(f"  Start Price: ${analysis.get('start_price', 0)}")
            print(f"  End Price: ${analysis.get('end_price', 0)}")
            print(f"  Highest Price: ${analysis.get('highest_price', 0)}")
            print(f"  Lowest Price: ${analysis.get('lowest_price', 0)}")
        
        # Print macro data if available
        if "macro_data" in analysis:
            print("\nMacroeconomic Environment:")
            macro = analysis["macro_data"]
            for key, value in macro.items():
                if not key.startswith("_"):  # Skip metadata fields
                    print(f"  {key}: {value}")
        
        # Print impact explanation if available
        if "impact_explanation" in analysis and analysis["impact_explanation"].get("success", False):
            print("\nImpact Explanation:")
            impact = analysis["impact_explanation"]
            print(f"  Immediate Reaction: {impact.get('immediate_reaction', '')}")
            print(f"  Causal Explanation: {impact.get('causal_explanation', '')}")
            print(f"  Follow-on Effects: {impact.get('follow_on_effects', '')}")
            
            if "macro_context" in impact:
                print(f"\n  Macroeconomic Context: {impact.get('macro_context', '')}")
            
            if "historical_pattern_analysis" in impact:
                print(f"\n  Historical Pattern Comparison: {impact.get('historical_pattern_analysis', '')}")
        
        # Print sentiment analysis if available
        if "sentiment_analysis" in analysis:
            print("\nSentiment Analysis:")
            sentiment = analysis["sentiment_analysis"]
            print(f"  Price-Based Sentiment: {sentiment['classified_sentiment']['label']} (score: {sentiment['classified_sentiment']['score']})")
            print(f"  Historical Sentiment: {sentiment['historical_sentiment']['label']} (score: {sentiment['historical_sentiment']['score']})")
            print(f"  Agreement: {sentiment['comparison']['agreement_label']} ({sentiment['comparison']['agreement']})")
            
            if "insights" in sentiment:
                print("\n  Sentiment Insights:")
                for insight in sentiment["insights"]:
                    print(f"    • {insight}")
            
    elif "pattern_summary" in analysis and "similar_events_count" in analysis:
        # Similar events analysis
        print(f"Similar Events Analysis - {analysis.get('pattern_summary', 'Unknown')}")
        print("-" * 80)
        
        # Pattern details
        print(f"Pattern: {analysis.get('pattern_summary', 'Unknown')}")
        print(f"Consistency: {analysis.get('consistency_score', 0)}%")
        print(f"Average Price Change: {analysis.get('avg_price_change', 0)}%")
        print(f"Average Maximum Drawdown: {analysis.get('avg_max_drawdown', 0)}%")
        print(f"Trend Distribution: {analysis.get('bullish_pct', 0)}% Bullish, {analysis.get('bearish_pct', 0)}% Bearish")
        print(f"Similar Events Count: {analysis.get('similar_events_count', 0)}")
        print(f"Most Common Sector: {analysis.get('dominant_sector', 'Unknown')}")
        print(f"Most Common Ticker: {analysis.get('dominant_ticker', 'Unknown')}")
        
        # Print sentiment analysis if available
        if analysis.get("has_sentiment_analysis", False):
            print("\nSentiment Pattern Analysis:")
            print(f"  Events with sentiment data: {analysis.get('events_with_sentiment', 0)}")
            print(f"  Sentiment-price alignment: {analysis.get('sentiment_alignment_pct', 0)}%")
            
            # Print performance comparison if available
            if "sentiment_performance" in analysis:
                perf = analysis["sentiment_performance"]
                print(f"\n  Performance when sentiment aligned with price: {perf.get('aligned_sentiment_avg_price_change', 0)}% ({perf.get('aligned_count', 0)} events)")
                print(f"  Performance when sentiment diverged from price: {perf.get('diverged_sentiment_avg_price_change', 0)}% ({perf.get('diverged_count', 0)} events)")
            
            # Print sentiment insights if available
            if "sentiment_insights" in analysis:
                print("\n  Sentiment Pattern Insights:")
                for i, insight in enumerate(analysis["sentiment_insights"], 1):
                    print(f"    {i}. {insight}")
        
        # Print macro analysis if available
        if analysis.get("has_macro_analysis", False):
            print("\nMacro Correlation Analysis:")
            print(f"  Events with macro data: {analysis.get('events_with_macro', 0)}")
            
            # Print correlations if available
            if "macro_correlations" in analysis:
                for factor, data in analysis["macro_correlations"].items():
                    if data.get("strength") != "None" and data.get("sample_size", 0) >= 3:
                        factor_display = {
                            'cpi': 'Inflation Rate',
                            'fed_rate': 'Fed Funds Rate',
                            'unemployment': 'Unemployment Rate',
                            'yield_curve': 'Yield Curve (10Y-2Y)'
                        }.get(factor, factor.title())
                        
                        print(f"  {factor_display}: {data.get('correlation')} correlation ({data.get('strength')} {data.get('direction')}) - sample size: {data.get('sample_size')}")
            
            # Print macro insights if available
            if "macro_insights" in analysis:
                print("\nMacro Environment Insights:")
                for i, insight in enumerate(analysis["macro_insights"], 1):
                    print(f"  {i}. {insight}")
    
    # Print metadata
    if "_metadata" in analysis:
        metadata = analysis["_metadata"]
        print("\nMetadata:")
        print(f"  Saved At: {metadata.get('saved_at', 'Unknown')}")
        if "query" in metadata:
            print(f"  Query: \"{metadata.get('query')}\"")
        print(f"  File Path: {metadata.get('file_path', 'Unknown')}")
    
    print("=" * 80)

def show_query_history(limit: int = 10, search: str = None) -> None:
    """
    Show query history
    
    Args:
        limit: Maximum number of queries to show
        search: Optional search term to filter by
    """
    persistence = ap.AnalysisPersistence()
    queries = persistence.search_query_history(query_term=search, limit=limit)
    
    if not queries:
        print("No queries found.")
        return
    
    print("\nQuery History:")
    print("-" * 80)
    
    for i, query in enumerate(reversed(queries), 1):
        q = query.get("query", "Unknown")
        timestamp = query.get("timestamp", "Unknown")
        result_type = query.get("result_type", "Unknown")
        
        print(f"{i}. \"{q}\" ({timestamp})")
        print(f"   Type: {result_type}")
        
        # Add additional details based on result type
        if result_type == "historical_event":
            ticker = query.get("ticker", "Unknown")
            event_date = query.get("event_date", "Unknown")
            print(f"   Analysis: {ticker} on {event_date}")
        elif result_type == "similar_events":
            pattern = query.get("pattern", "Unknown")
            ticker = query.get("dominant_ticker", "Unknown")
            print(f"   Analysis: {pattern} - {ticker}")
        
        print(f"   File: {query.get('file_path', 'Unknown')}")
        print()

def show_statistics() -> None:
    """Show statistics about saved analyses"""
    persistence = ap.AnalysisPersistence()
    stats = persistence.get_statistics()
    
    print("\nAnalysis Storage Statistics:")
    print("-" * 80)
    print(f"Total Historical Event Analyses: {stats.get('total_historical_events', 0)}")
    print(f"Total Similar Events Analyses: {stats.get('total_similar_events', 0)}")
    print(f"Total Queries: {stats.get('total_queries', 0)}")
    
    if stats.get("tickers_analyzed"):
        print(f"Tickers Analyzed: {', '.join(stats.get('tickers_analyzed', []))}")
    
    if stats.get("most_analyzed_ticker"):
        print(f"Most Analyzed Ticker: {stats.get('most_analyzed_ticker')}")
    
    if stats.get("most_common_pattern"):
        print(f"Most Common Pattern: {stats.get('most_common_pattern')}")
    
    if stats.get("most_recent_query"):
        print(f"Most Recent Query: \"{stats.get('most_recent_query')}\"")

def export_analyses(output_file: str, ticker: str = None, pattern: str = None) -> None:
    """
    Export analyses to a file
    
    Args:
        output_file: Path to the output file
        ticker: Optional ticker to filter by
        pattern: Optional pattern to filter by
    """
    persistence = ap.AnalysisPersistence()
    
    # Get analyses to export
    export_data = {
        "historical_events": [],
        "similar_events": [],
        "export_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "filter": {"ticker": ticker, "pattern": pattern}
    }
    
    # Get historical event analyses
    if ticker:
        historical_analyses = persistence.find_historical_analysis(ticker=ticker)
    else:
        historical_analyses = []
        for ticker_analyses in persistence.event_index["events"].values():
            historical_analyses.extend(ticker_analyses)
    
    # Load full analyses for export
    for analysis_info in historical_analyses:
        file_path = analysis_info.get("file_path", "")
        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, 'r') as f:
                    full_analysis = json.load(f)
                    export_data["historical_events"].append(full_analysis)
            except Exception as e:
                print(f"Error loading analysis from {file_path}: {str(e)}")
    
    # Get similar events analyses
    if pattern:
        similar_analyses = persistence.find_similar_events_analysis(pattern=pattern)
    else:
        similar_analyses = []
        for pattern_analyses in persistence.event_index["similar_events"].values():
            similar_analyses.extend(pattern_analyses)
    
    # Load full analyses for export
    for analysis_info in similar_analyses:
        file_path = analysis_info.get("file_path", "")
        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, 'r') as f:
                    full_analysis = json.load(f)
                    export_data["similar_events"].append(full_analysis)
            except Exception as e:
                print(f"Error loading analysis from {file_path}: {str(e)}")
    
    # Save to output file
    try:
        with open(output_file, 'w') as f:
            json.dump(export_data, f, indent=2)
        print(f"Exported {len(export_data['historical_events'])} historical event analyses and {len(export_data['similar_events'])} similar events analyses to {output_file}")
    except Exception as e:
        print(f"Error exporting analyses to {output_file}: {str(e)}")

def delete_analysis(file_path: str) -> None:
    """
    Delete a specific analysis
    
    Args:
        file_path: Path to the analysis file
    """
    if not os.path.exists(file_path):
        print(f"Analysis file not found: {file_path}")
        return
    
    # Confirm deletion
    confirm = input(f"Are you sure you want to delete {file_path}? (y/n): ")
    if confirm.lower() != 'y':
        print("Deletion cancelled.")
        return
    
    try:
        # Delete the file
        os.remove(file_path)
        print(f"Deleted {file_path}")
        
        # Update the index - this is a bit trickier and requires a full reindex
        # For simplicity, we'll just notify the user that they should reindex
        print("NOTE: The index may be out of sync. Run 'reindex' command to update the index.")
    except Exception as e:
        print(f"Error deleting analysis: {str(e)}")

def reindex() -> None:
    """Rebuild the analysis index from scratch by scanning the directory"""
    # Create a new persistence instance with a temporary index file
    temp_index_file = "temp_index.json"
    persistence = ap.AnalysisPersistence(index_file=temp_index_file)
    
    # Initialize empty index
    persistence.event_index = {
        "events": {},
        "similar_events": {},
        "last_updated": "",
        "query_history": []
    }
    
    # Scan events directory
    events_dir = os.path.join(persistence.base_dir, "events")
    if os.path.exists(events_dir):
        for filename in os.listdir(events_dir):
            if filename.endswith(".json"):
                file_path = os.path.join(events_dir, filename)
                try:
                    # Load the analysis
                    with open(file_path, 'r') as f:
                        analysis = json.load(f)
                    
                    # Check if it's a valid analysis
                    if analysis.get("success", False) and "ticker" in analysis and "event_date" in analysis:
                        # Add metadata if missing
                        if "_metadata" not in analysis:
                            analysis["_metadata"] = {
                                "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "query": None,
                                "file_path": file_path
                            }
                        
                        # Save it back to ensure metadata is present
                        with open(file_path, 'w') as f:
                            json.dump(analysis, f, indent=2)
                        
                        # Add to index
                        ticker = analysis.get("ticker", "unknown")
                        event_date = analysis.get("event_date", "unknown")
                        
                        if ticker not in persistence.event_index["events"]:
                            persistence.event_index["events"][ticker] = []
                        
                        persistence.event_index["events"][ticker].append({
                            "event_date": event_date,
                            "price_change": analysis.get("price_change_pct", 0),
                            "trend": analysis.get("trend", "Unknown"),
                            "file_path": file_path,
                            "saved_at": analysis["_metadata"]["saved_at"]
                        })
                        
                        # Add to query history if query is available
                        if analysis["_metadata"].get("query"):
                            query_entry = {
                                "query": analysis["_metadata"]["query"],
                                "timestamp": analysis["_metadata"]["saved_at"],
                                "result_type": "historical_event",
                                "ticker": ticker,
                                "event_date": event_date,
                                "file_path": file_path
                            }
                            persistence.event_index["query_history"].append(query_entry)
                except Exception as e:
                    print(f"Error processing {file_path}: {str(e)}")
    
    # Scan similar events directory
    similar_dir = os.path.join(persistence.base_dir, "similar_events")
    if os.path.exists(similar_dir):
        for filename in os.listdir(similar_dir):
            if filename.endswith(".json"):
                file_path = os.path.join(similar_dir, filename)
                try:
                    # Load the analysis
                    with open(file_path, 'r') as f:
                        analysis = json.load(f)
                    
                    # Check if it's a valid analysis
                    if analysis.get("success", False) and "pattern_summary" in analysis:
                        # Add metadata if missing
                        if "_metadata" not in analysis:
                            analysis["_metadata"] = {
                                "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "query": None,
                                "file_path": file_path
                            }
                        
                        # Save it back to ensure metadata is present
                        with open(file_path, 'w') as f:
                            json.dump(analysis, f, indent=2)
                        
                        # Add to index
                        pattern = analysis.get("pattern_summary", "unknown_pattern")
                        ticker = analysis.get("dominant_ticker", "unknown")
                        
                        if pattern not in persistence.event_index["similar_events"]:
                            persistence.event_index["similar_events"][pattern] = []
                        
                        persistence.event_index["similar_events"][pattern].append({
                            "dominant_ticker": ticker,
                            "avg_price_change": analysis.get("avg_price_change", 0),
                            "consistency_score": analysis.get("consistency_score", 0),
                            "file_path": file_path,
                            "saved_at": analysis["_metadata"]["saved_at"]
                        })
                        
                        # Add to query history if query is available
                        if analysis["_metadata"].get("query"):
                            query_entry = {
                                "query": analysis["_metadata"]["query"],
                                "timestamp": analysis["_metadata"]["saved_at"],
                                "result_type": "similar_events",
                                "pattern": pattern,
                                "dominant_ticker": ticker,
                                "file_path": file_path
                            }
                            persistence.event_index["query_history"].append(query_entry)
                except Exception as e:
                    print(f"Error processing {file_path}: {str(e)}")
    
    # Sort query history by timestamp
    persistence.event_index["query_history"].sort(key=lambda x: x.get("timestamp", ""))
    
    # Save the index
    persistence._save_index()
    
    # Replace the real index file with the temporary one
    real_index_path = os.path.join(persistence.base_dir, ap.DEFAULT_INDEX_FILE)
    temp_index_path = os.path.join(persistence.base_dir, temp_index_file)
    
    if os.path.exists(real_index_path):
        os.replace(temp_index_path, real_index_path)
    else:
        os.rename(temp_index_path, real_index_path)
    
    # Print statistics
    stats = persistence.get_statistics()
    print(f"Reindexed {stats.get('total_historical_events', 0)} historical event analyses and {stats.get('total_similar_events', 0)} similar events analyses.")
    print(f"Total queries in history: {stats.get('total_queries', 0)}")

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="View and manage saved analyses")
    
    # Create subparsers for different commands
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List saved analyses")
    list_parser.add_argument("--ticker", "-t", help="Filter by ticker symbol")
    list_parser.add_argument("--pattern", "-p", help="Filter by pattern")
    list_parser.add_argument("--days", "-d", type=int, default=30, help="Number of recent days to include")
    list_parser.add_argument("--limit", "-l", type=int, default=10, help="Maximum number of analyses to show")
    list_parser.add_argument("--detailed", action="store_true", help="Show detailed information")
    
    # Show command
    show_parser = subparsers.add_parser("show", help="Show a specific analysis")
    show_parser.add_argument("file_path", help="Path to the analysis file")
    show_parser.add_argument("--format", "-f", choices=["text", "json"], default="text", help="Output format")
    
    # History command
    history_parser = subparsers.add_parser("history", help="Show query history")
    history_parser.add_argument("--limit", "-l", type=int, default=10, help="Maximum number of queries to show")
    history_parser.add_argument("--search", "-s", help="Search term to filter by")
    
    # Stats command
    subparsers.add_parser("stats", help="Show statistics about saved analyses")
    
    # Export command
    export_parser = subparsers.add_parser("export", help="Export analyses to a file")
    export_parser.add_argument("output_file", help="Path to the output file")
    export_parser.add_argument("--ticker", "-t", help="Filter by ticker symbol")
    export_parser.add_argument("--pattern", "-p", help="Filter by pattern")
    
    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a specific analysis")
    delete_parser.add_argument("file_path", help="Path to the analysis file")
    
    # Reindex command
    subparsers.add_parser("reindex", help="Rebuild the analysis index")
    
    return parser.parse_args()

def main():
    """Main function"""
    args = parse_args()
    
    # Execute the appropriate command
    if args.command == "list":
        list_analyses(ticker=args.ticker, days=args.days, pattern=args.pattern, 
                     limit=args.limit, detailed=args.detailed)
    elif args.command == "show":
        show_analysis(file_path=args.file_path, format=args.format)
    elif args.command == "history":
        show_query_history(limit=args.limit, search=args.search)
    elif args.command == "stats":
        show_statistics()
    elif args.command == "export":
        export_analyses(output_file=args.output_file, ticker=args.ticker, pattern=args.pattern)
    elif args.command == "delete":
        delete_analysis(file_path=args.file_path)
    elif args.command == "reindex":
        reindex()
    else:
        # No command or unrecognized command
        print("Please specify a command. Use --help for more information.")
        sys.exit(1)

if __name__ == "__main__":
    main() 