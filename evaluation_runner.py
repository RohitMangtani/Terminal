#!/usr/bin/env python
"""
TRADE EVALUATION RUNNER
======================

This script runs the trade evaluator on historical trades and saves evaluation results.
It loads trades from trade_history.json, evaluates each one, and saves the results
to evaluated_trades.json for later analysis.

How to Run:
----------
python evaluation_runner.py

Additional Options:
-----------------
--input FILE   : Specify a custom input file (default: trade_history.json)
--output FILE  : Specify a custom output file (default: evaluated_trades.json)
--days DAYS    : Number of trading days to evaluate (default: 7)
--force        : Re-evaluate all trades, even if they were already evaluated
--verbose      : Show detailed output during processing

What This Does:
-------------
1. Loads historical trades from trade_history.json
2. Skips trades with future dates that cannot be evaluated yet
3. Evaluates each trade using actual market data
4. Adds evaluation metrics to each trade
5. Saves the evaluated trades to evaluated_trades.json
6. Prints a summary of evaluation results
"""

import json
import os
import sys
import argparse
from datetime import datetime
from typing import Dict, List, Any
import pandas as pd

# Import evaluation functions
from evaluator import evaluate_trade, evaluate_trade_history, calculate_success_rate, parse_timestamp
from logger import get_logger, log_start_section, log_end_section

# Initialize logger
logger = get_logger(__name__)

# Constants
DEFAULT_INPUT_FILE = "trade_history.json"
DEFAULT_OUTPUT_FILE = "evaluated_trades.json"
DEFAULT_EVALUATION_DAYS = 7

def load_trades(input_file: str = DEFAULT_INPUT_FILE) -> List[Dict[str, Any]]:
    """Load trades from the input file."""
    try:
        if not os.path.exists(input_file):
            logger.error(f"Input file not found: {input_file}")
            return []
            
        with open(input_file, 'r') as f:
            trades = json.load(f)
            
        if not isinstance(trades, list):
            logger.error(f"Invalid format in {input_file}: expected a list of trades")
            return []
            
        logger.info(f"Loaded {len(trades)} trades from {input_file}")
        return trades
    except Exception as e:
        logger.error(f"Error loading trades: {str(e)}")
        return []

def save_evaluated_trades(evaluated_trades: List[Dict[str, Any]], 
                         output_file: str = DEFAULT_OUTPUT_FILE) -> bool:
    """Save evaluated trades to the output file."""
    try:
        with open(output_file, 'w') as f:
            json.dump(evaluated_trades, f, indent=2)
            
        logger.info(f"Saved {len(evaluated_trades)} evaluated trades to {output_file}")
        return True
    except Exception as e:
        logger.error(f"Error saving evaluated trades: {str(e)}")
        return False

def filter_future_trades(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter out trades with future timestamps."""
    now = datetime.now()
    past_trades = []
    future_trades = []
    
    for trade in trades:
        timestamp = trade.get('saved_timestamp')
        if not timestamp:
            # If no timestamp, assume it's from the past
            past_trades.append(trade)
            continue
            
        try:
            trade_date = parse_timestamp(timestamp)
            if trade_date > now:
                future_trades.append(trade)
            else:
                past_trades.append(trade)
        except Exception:
            # If can't parse timestamp, assume it's from the past
            past_trades.append(trade)
    
    if future_trades:
        logger.info(f"Skipping {len(future_trades)} trades with future timestamps")
        
    return past_trades

def filter_already_evaluated(trades: List[Dict[str, Any]], force: bool = False) -> List[Dict[str, Any]]:
    """Filter out trades that have already been evaluated."""
    if force:
        return trades
        
    to_evaluate = []
    already_evaluated = []
    
    for trade in trades:
        if 'evaluation' in trade:
            already_evaluated.append(trade)
        else:
            to_evaluate.append(trade)
    
    if already_evaluated:
        logger.info(f"Skipping {len(already_evaluated)} trades that have already been evaluated")
        
    return to_evaluate

def print_evaluation_summary(evaluated_trades):
    """Print a summary of the evaluation results."""
    if not evaluated_trades:
        logger.info("No trades to summarize")
        return

    total = len(evaluated_trades)
    correct = sum(1 for t in evaluated_trades if t.get('evaluation', {}).get('trade_direction_correct', False))
    success_rate = (correct / total) * 100 if total > 0 else 0
    
    avg_movement = sum(abs(t.get('evaluation', {}).get('actual_move_pct', 0)) for t in evaluated_trades) / total if total > 0 else 0
    
    # Count by option type
    call_trades = [t for t in evaluated_trades if t.get('trade_idea', {}).get('option_type') == 'CALL']
    put_trades = [t for t in evaluated_trades if t.get('trade_idea', {}).get('option_type') == 'PUT']
    
    call_correct = sum(1 for t in call_trades if t.get('evaluation', {}).get('trade_direction_correct', False))
    put_correct = sum(1 for t in put_trades if t.get('evaluation', {}).get('trade_direction_correct', False))
    
    call_success = (call_correct / len(call_trades)) * 100 if call_trades else 0
    put_success = (put_correct / len(put_trades)) * 100 if put_trades else 0
    
    logger.info("============================================================")
    logger.info("TRADE EVALUATION SUMMARY")
    logger.info("============================================================")
    logger.info(f"Total trades evaluated: {total}")
    logger.info(f"Overall success rate: {success_rate:.1f}%")
    logger.info(f"Average price movement: {avg_movement:.1f}%")
    logger.info(f"CALL trades: {len(call_trades)} ({call_success:.1f}% successful)")
    logger.info(f"PUT trades: {len(put_trades)} ({put_success:.1f}% successful)")
    logger.info("============================================================")
    
    logger.info("\nMost recent trade evaluations:")
    for trade in evaluated_trades[-5:]:  # Show the 5 most recent
        ticker = trade.get('trade_idea', {}).get('ticker', 'Unknown')
        option_type = trade.get('trade_idea', {}).get('option_type', 'Unknown')
        actual_move = trade.get('evaluation', {}).get('actual_move_pct', 0)
        correct = trade.get('evaluation', {}).get('trade_direction_correct', False)
        
        # Using ASCII characters instead of Unicode for better compatibility
        result_symbol = '+' if correct else '-'
        logger.info(f"- {ticker} {option_type}: {actual_move:.1f}% move, {result_symbol}")

def load_existing_evaluations(output_file: str = DEFAULT_OUTPUT_FILE) -> Dict[str, Dict[str, Any]]:
    """Load existing evaluations as a dictionary for quick lookup."""
    if not os.path.exists(output_file):
        return {}
        
    try:
        with open(output_file, 'r') as f:
            evaluated_trades = json.load(f)
            
        # Create a dictionary for quick lookup
        evaluations = {}
        for trade in evaluated_trades:
            # Use trade timestamp and ticker as a unique identifier
            trade_id = f"{trade.get('saved_timestamp', '')}-{trade.get('trade_idea', {}).get('ticker', '')}"
            evaluations[trade_id] = trade.get('evaluation', {})
            
        logger.info(f"Loaded {len(evaluations)} existing evaluations from {output_file}")
        return evaluations
    except Exception as e:
        logger.error(f"Error loading existing evaluations: {str(e)}")
        return {}

def merge_evaluations(trades: List[Dict[str, Any]], 
                     existing_evaluations: Dict[str, Dict[str, Any]], 
                     force: bool = False) -> List[Dict[str, Any]]:
    """Merge existing evaluations with trades that need to be evaluated."""
    to_evaluate = []
    already_evaluated = []
    
    for trade in trades:
        # Skip if already has evaluation and not forcing
        if 'evaluation' in trade and not force:
            already_evaluated.append(trade)
            continue
            
        # Try to find existing evaluation
        trade_id = f"{trade.get('saved_timestamp', '')}-{trade.get('trade_idea', {}).get('ticker', '')}"
        if not force and trade_id in existing_evaluations:
            # Use existing evaluation
            trade['evaluation'] = existing_evaluations[trade_id]
            already_evaluated.append(trade)
        else:
            # Needs evaluation
            to_evaluate.append(trade)
    
    logger.info(f"Found {len(already_evaluated)} previously evaluated trades")
    logger.info(f"Need to evaluate {len(to_evaluate)} trades")
    
    return to_evaluate, already_evaluated

def run_evaluation(input_file: str = DEFAULT_INPUT_FILE, 
                  output_file: str = DEFAULT_OUTPUT_FILE, 
                  days: int = DEFAULT_EVALUATION_DAYS,
                  force: bool = False,
                  verbose: bool = False) -> None:
    """
    Run the evaluation process on trades.
    
    Args:
        input_file: Path to the input JSON file with trades
        output_file: Path to the output JSON file for evaluated trades
        days: Number of trading days to evaluate
        force: Whether to force re-evaluation of all trades
        verbose: Whether to show detailed output
    """
    log_start_section("Trade Evaluation")
    logger.info(f"Starting trade evaluation process")
    logger.info(f"Input file: {input_file}")
    logger.info(f"Output file: {output_file}")
    logger.info(f"Evaluation period: {days} trading days")
    
    # Load trades from input file
    trades = load_trades(input_file)
    if not trades:
        logger.error("No trades to evaluate. Exiting.")
        return
    
    # Filter out future trades
    past_trades = filter_future_trades(trades)
    if not past_trades:
        logger.error("No past trades to evaluate. Exiting.")
        return
    
    # Load existing evaluations if available
    existing_evaluations = load_existing_evaluations(output_file)
    
    # Split trades that need evaluation from those already evaluated
    to_evaluate, already_evaluated = merge_evaluations(past_trades, existing_evaluations, force)
    
    # Evaluate trades
    newly_evaluated = []
    if to_evaluate:
        logger.info(f"Evaluating {len(to_evaluate)} trades...")
        newly_evaluated = evaluate_trade_history(to_evaluate, days)
        logger.info(f"Completed evaluation of {len(newly_evaluated)} trades")
    
    # Combine with already evaluated trades
    all_evaluated_trades = already_evaluated + newly_evaluated
    
    # Save all evaluated trades
    if all_evaluated_trades:
        save_evaluated_trades(all_evaluated_trades, output_file)
        print_evaluation_summary(all_evaluated_trades)
    else:
        logger.warning("No trades were evaluated")
    
    log_end_section("Trade Evaluation")

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Evaluate historical trades")
    parser.add_argument("--input", type=str, default=DEFAULT_INPUT_FILE,
                       help=f"Input file with trades (default: {DEFAULT_INPUT_FILE})")
    parser.add_argument("--output", type=str, default=DEFAULT_OUTPUT_FILE,
                       help=f"Output file for evaluated trades (default: {DEFAULT_OUTPUT_FILE})")
    parser.add_argument("--days", type=int, default=DEFAULT_EVALUATION_DAYS,
                       help=f"Number of trading days to evaluate (default: {DEFAULT_EVALUATION_DAYS})")
    parser.add_argument("--force", action="store_true",
                       help="Force re-evaluation of all trades")
    parser.add_argument("--verbose", action="store_true",
                       help="Show detailed output during processing")
    
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    
    run_evaluation(
        input_file=args.input,
        output_file=args.output,
        days=args.days,
        force=args.force,
        verbose=args.verbose
    ) 