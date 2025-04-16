"""
Sentiment Analyzer Module

This module handles fetching, analyzing, and comparing sentiment data from various sources
including news articles and social media platforms. It allows for comparison between
classified sentiment from our system and historical sentiment from external sources.
"""

import os
import json
import datetime
import requests
from typing import Dict, List, Tuple, Optional, Union, Any
import pandas as pd
import numpy as np
from collections import defaultdict
import logging
from datetime import datetime, timedelta

# Constants
DEFAULT_SENTIMENT_CACHE_FILE = "sentiment_data_cache.json"
CACHE_EXPIRY_HOURS = 24
DEFAULT_LOOKBACK_DAYS = 30
DEFAULT_SENTIMENT_SOURCES = ["news", "social_media", "analyst_ratings"]
SENTIMENT_SCORE_RANGE = (-1.0, 1.0)  # -1 for very bearish, +1 for very bullish

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SentimentCache:
    """Handles caching of sentiment data to minimize API calls"""
    
    def __init__(self, cache_file: str = DEFAULT_SENTIMENT_CACHE_FILE):
        self.cache_file = cache_file
        self.cache_data = self._load_cache()
    
    def _load_cache(self) -> Dict:
        """Load cache from file or create empty cache"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                    logger.info(f"Loaded sentiment cache from {self.cache_file}")
                    return data
            except Exception as e:
                logger.error(f"Error loading sentiment cache: {str(e)}")
                return {"last_updated": "", "data": {}}
        else:
            logger.info(f"Creating new sentiment cache")
            return {"last_updated": "", "data": {}}
    
    def save_cache(self) -> None:
        """Save current cache to file"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache_data, f, indent=2)
            logger.info(f"Saved sentiment cache to {self.cache_file}")
        except Exception as e:
            logger.error(f"Error saving sentiment cache: {str(e)}")
    
    def get_cached_sentiment(self, ticker: str, date: str) -> Optional[Dict]:
        """Retrieve cached sentiment for ticker and date if available and not expired"""
        cache_key = f"{ticker}_{date}"
        if cache_key in self.cache_data["data"]:
            entry = self.cache_data["data"][cache_key]
            cache_date = datetime.strptime(entry["timestamp"], "%Y-%m-%d %H:%M:%S")
            now = datetime.now()
            if (now - cache_date).total_seconds() < CACHE_EXPIRY_HOURS * 3600:
                logger.info(f"Using cached sentiment data for {ticker} on {date}")
                return entry
        return None
    
    def add_to_cache(self, ticker: str, date: str, sentiment_data: Dict) -> None:
        """Add sentiment data to cache"""
        cache_key = f"{ticker}_{date}"
        sentiment_data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.cache_data["data"][cache_key] = sentiment_data
        self.cache_data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save_cache()


def get_historical_sentiment(
    ticker: str, 
    date: str, 
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    sources: List[str] = DEFAULT_SENTIMENT_SOURCES
) -> Dict:
    """
    Fetch historical sentiment data for a ticker around a specific date.
    
    Args:
        ticker: The stock/crypto ticker symbol
        date: Date in YYYY-MM-DD format
        lookback_days: Number of days to look back for sentiment data
        sources: List of sentiment sources to include
        
    Returns:
        Dict containing sentiment scores and volumes by source
    """
    # Initialize sentiment cache
    cache = SentimentCache()
    
    # Check if we have cached data
    cached_data = cache.get_cached_sentiment(ticker, date)
    if cached_data:
        return cached_data
    
    # Convert date string to datetime
    try:
        date_obj = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        logger.error(f"Invalid date format: {date}. Expected YYYY-MM-DD.")
        return {
            "success": False,
            "error": f"Invalid date format: {date}. Expected YYYY-MM-DD."
        }
    
    # Calculate date range
    start_date = (date_obj - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    end_date = date_obj.strftime("%Y-%m-%d")
    
    # In production, this would fetch data from APIs like:
    # - News APIs (GDELT, NewsAPI)
    # - Social media sentiment (Twitter/X API)
    # - Financial platforms (StockTwits, etc.)
    
    # For simulation purposes, generate synthetic sentiment data
    sentiment_data = _generate_synthetic_sentiment(ticker, start_date, end_date, sources)
    
    # Cache the results
    cache.add_to_cache(ticker, date, sentiment_data)
    
    return sentiment_data


def _generate_synthetic_sentiment(ticker: str, start_date: str, end_date: str, sources: List[str]) -> Dict:
    """
    Generate synthetic sentiment data for demonstration purposes.
    In production, this would be replaced with actual API calls.
    
    Args:
        ticker: Stock/crypto ticker
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        sources: List of sentiment sources to include
        
    Returns:
        Dict with synthetic sentiment data
    """
    # Parse dates to create range
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    date_range = [(start + timedelta(days=x)).strftime("%Y-%m-%d") 
                 for x in range((end - start).days + 1)]
    
    # Create source-specific sentiment trends
    sentiment_by_source = {}
    
    # Add baseline sentiment based on ticker
    if "BTC" in ticker or "ETH" in ticker:
        base_sentiment = 0.3  # Crypto tends to have more bullish social sentiment
    elif ticker in ["SPY", "QQQ", "DIA"]:
        base_sentiment = 0.1  # Market indexes have slightly positive bias
    else:
        base_sentiment = 0.0  # Neutral baseline for other tickers
    
    # Create synthetic data for each source
    for source in sources:
        daily_data = []
        
        # Different volatility and bias for different sources
        if source == "news":
            volatility = 0.2
            source_bias = -0.1  # News tends to be slightly more negative
        elif source == "social_media":
            volatility = 0.4 
            source_bias = 0.2   # Social media tends to be more positive and volatile
        else:  # analyst_ratings
            volatility = 0.15
            source_bias = 0.0   # Analyst ratings are more balanced but less volatile
        
        # Create a believable trend
        sentiment_value = base_sentiment + source_bias
        for date in date_range:
            # Add some randomness but maintain a trend
            sentiment_value += np.random.normal(0, volatility) * 0.3
            # Keep within bounds
            sentiment_value = max(min(sentiment_value, 0.95), -0.95)
            
            # Generate volume data (higher at event date)
            days_to_event = abs((datetime.strptime(date, "%Y-%m-%d") - 
                               datetime.strptime(end_date, "%Y-%m-%d")).days)
            
            # Volume peaks near the event date
            volume_factor = 1.0 + max(0, (5 - days_to_event) / 5.0)
            base_volume = {
                "news": 50,
                "social_media": 500,
                "analyst_ratings": 10
            }.get(source, 100)
            
            volume = int(base_volume * volume_factor * (1 + np.random.random() * 0.5))
            
            daily_data.append({
                "date": date,
                "sentiment_score": round(sentiment_value, 2),
                "volume": volume,
                "source_count": max(3, int(volume / 10))  # Number of sources analyzed
            })
        
        sentiment_by_source[source] = daily_data
    
    # Calculate aggregated sentiment score
    aggr_sentiment = _calculate_aggregate_sentiment(sentiment_by_source, end_date)
    
    return {
        "success": True,
        "ticker": ticker,
        "period": f"{start_date} to {end_date}",
        "sentiment_by_source": sentiment_by_source,
        "aggregate_sentiment": aggr_sentiment,
        "last_day_sentiment": _get_last_day_sentiment(sentiment_by_source, end_date)
    }


def _calculate_aggregate_sentiment(sentiment_by_source: Dict, target_date: str) -> Dict:
    """
    Calculate weighted aggregate sentiment across all sources.
    
    Args:
        sentiment_by_source: Dict of sentiment data by source
        target_date: Target date for sentiment aggregation
        
    Returns:
        Dict with aggregate sentiment metrics
    """
    # Weighting factors for different sources
    source_weights = {
        "news": 0.4,
        "social_media": 0.35,
        "analyst_ratings": 0.25
    }
    
    # Initialize aggregation variables
    total_weighted_score = 0.0
    total_weight = 0.0
    total_volume = 0
    source_contributions = {}
    
    # Process each source
    for source, data in sentiment_by_source.items():
        # Get source weight or default to 0.2
        weight = source_weights.get(source, 0.2)
        
        # Find the last day data for each source
        last_day_data = next((d for d in data if d["date"] == target_date), None)
        if not last_day_data:
            continue
        
        # Calculate weighted score
        source_score = last_day_data["sentiment_score"]
        source_volume = last_day_data["volume"]
        weighted_score = source_score * weight
        
        # Add to totals
        total_weighted_score += weighted_score
        total_weight += weight
        total_volume += source_volume
        
        # Track source contribution
        source_contributions[source] = {
            "score": source_score,
            "weighted_contribution": weighted_score,
            "volume": source_volume
        }
    
    # Normalize if we have valid weights
    if total_weight > 0:
        normalized_score = total_weighted_score / total_weight
    else:
        normalized_score = 0.0
    
    # Create aggregate sentiment result
    sentiment_label = _score_to_sentiment_label(normalized_score)
    
    return {
        "score": round(normalized_score, 2),
        "label": sentiment_label,
        "total_volume": total_volume,
        "source_count": len(source_contributions),
        "source_contributions": source_contributions
    }


def _get_last_day_sentiment(sentiment_by_source: Dict, target_date: str) -> Dict:
    """Extract sentiment data for just the target date across all sources"""
    result = {}
    for source, data in sentiment_by_source.items():
        last_day = next((d for d in data if d["date"] == target_date), None)
        if last_day:
            result[source] = last_day
    return result


def _score_to_sentiment_label(score: float) -> str:
    """Convert a numerical sentiment score to a sentiment label"""
    if score >= 0.6:
        return "Very Bullish"
    elif score >= 0.2:
        return "Bullish"
    elif score >= -0.2:
        return "Neutral"
    elif score >= -0.6:
        return "Bearish"
    else:
        return "Very Bearish"


def compare_sentiment(
    classified_sentiment: str, 
    ticker: str, 
    event_date: str
) -> Dict:
    """
    Compare our classified sentiment with historical sentiment data.
    
    Args:
        classified_sentiment: The sentiment classification from our system ("Bullish", "Bearish", "Neutral")
        ticker: The stock/crypto ticker symbol
        event_date: Date of the event in YYYY-MM-DD format
        
    Returns:
        Dict containing sentiment comparison results
    """
    # Standardize sentiment values
    if not classified_sentiment or classified_sentiment.lower() not in ["bullish", "bearish", "neutral"]:
        classified_sentiment = "Neutral"
    else:
        classified_sentiment = classified_sentiment.capitalize()
    
    # Get historical sentiment data
    historical_data = get_historical_sentiment(ticker, event_date)
    
    if not historical_data.get("success", False):
        return {
            "success": False,
            "error": historical_data.get("error", "Failed to retrieve historical sentiment data")
        }
    
    # Get the aggregate sentiment from historical data
    hist_sentiment = historical_data["aggregate_sentiment"]
    hist_sentiment_label = hist_sentiment["label"]
    
    # Calculate the numerical score for our classified sentiment
    classified_score = _sentiment_label_to_score(classified_sentiment)
    
    # Calculate agreement and divergence
    agreement_score = _calculate_sentiment_agreement(classified_sentiment, hist_sentiment_label)
    numerical_divergence = abs(classified_score - hist_sentiment["score"])
    
    # Prepare sentiment trend data
    sentiment_trend = _extract_sentiment_trend(historical_data)
    
    # Generate insights about the comparison
    insights = _generate_sentiment_insights(
        classified_sentiment, 
        hist_sentiment_label,
        numerical_divergence,
        historical_data
    )
    
    return {
        "success": True,
        "classified_sentiment": {
            "label": classified_sentiment,
            "score": classified_score
        },
        "historical_sentiment": {
            "label": hist_sentiment_label,
            "score": hist_sentiment["score"],
            "source_count": hist_sentiment["source_count"],
            "total_volume": hist_sentiment["total_volume"]
        },
        "comparison": {
            "agreement": agreement_score,
            "agreement_label": _agreement_score_to_label(agreement_score),
            "numerical_divergence": round(numerical_divergence, 2),
            "sentiment_trend": sentiment_trend
        },
        "insights": insights,
        "raw_historical_data": historical_data
    }


def _sentiment_label_to_score(sentiment: str) -> float:
    """Convert a sentiment label to a numerical score"""
    score_map = {
        "Very Bullish": 0.8,
        "Bullish": 0.4,
        "Neutral": 0.0,
        "Bearish": -0.4,
        "Very Bearish": -0.8
    }
    return score_map.get(sentiment, 0.0)


def _calculate_sentiment_agreement(sentiment1: str, sentiment2: str) -> float:
    """Calculate agreement score between two sentiment labels"""
    # Map sentiment labels to numerical values
    sentiment_values = {
        "Very Bullish": 2,
        "Bullish": 1,
        "Neutral": 0,
        "Bearish": -1,
        "Very Bearish": -2
    }
    
    # Get numerical values
    val1 = sentiment_values.get(sentiment1, 0)
    val2 = sentiment_values.get(sentiment2, 0)
    
    # Calculate agreement (1.0 = perfect agreement, 0.0 = complete disagreement)
    max_diff = 4  # Maximum possible difference between sentiments
    actual_diff = abs(val1 - val2)
    
    # Convert to agreement score (1.0 = perfect agreement, 0.0 = complete disagreement)
    agreement = 1.0 - (actual_diff / max_diff)
    
    return round(agreement, 2)


def _agreement_score_to_label(score: float) -> str:
    """Convert agreement score to descriptive label"""
    if score >= 0.9:
        return "Perfect Agreement"
    elif score >= 0.7:
        return "Strong Agreement"
    elif score >= 0.5:
        return "Moderate Agreement"
    elif score >= 0.3:
        return "Weak Agreement"
    else:
        return "Disagreement"


def _extract_sentiment_trend(historical_data: Dict) -> Dict:
    """
    Extract sentiment trend from historical data.
    
    Args:
        historical_data: Dictionary containing historical sentiment data
        
    Returns:
        Dict with trend analysis
    """
    trend_data = {}
    
    for source, data in historical_data["sentiment_by_source"].items():
        # Sort data by date
        sorted_data = sorted(data, key=lambda x: x["date"])
        
        if len(sorted_data) < 2:
            continue
            
        # Calculate trend (last half vs first half)
        midpoint = len(sorted_data) // 2
        first_half = sorted_data[:midpoint]
        second_half = sorted_data[midpoint:]
        
        avg_first = sum(d["sentiment_score"] for d in first_half) / len(first_half)
        avg_second = sum(d["sentiment_score"] for d in second_half) / len(second_half)
        
        # Calculate trend direction and strength
        trend_direction = "improving" if avg_second > avg_first else "deteriorating"
        trend_strength = abs(avg_second - avg_first)
        
        trend_data[source] = {
            "direction": trend_direction,
            "strength": round(trend_strength, 2),
            "early_period_avg": round(avg_first, 2),
            "late_period_avg": round(avg_second, 2)
        }
    
    return trend_data


def _generate_sentiment_insights(
    classified_sentiment: str, 
    historical_sentiment: str,
    divergence: float,
    historical_data: Dict
) -> List[str]:
    """
    Generate insights about sentiment comparison.
    
    Args:
        classified_sentiment: Our system's sentiment classification
        historical_sentiment: Historical sentiment from data
        divergence: Numerical divergence between sentiments
        historical_data: Full historical sentiment data
        
    Returns:
        List of insight strings
    """
    insights = []
    
    # Check for agreement/disagreement
    if divergence < 0.3:
        insights.append(
            f"Your classification ({classified_sentiment}) aligns well with historical sentiment data ({historical_sentiment})."
        )
    elif divergence < 0.6:
        insights.append(
            f"Your classification ({classified_sentiment}) partially aligns with historical sentiment data ({historical_sentiment})."
        )
    else:
        insights.append(
            f"Your classification ({classified_sentiment}) significantly differs from historical sentiment ({historical_sentiment})."
        )
    
    # Add source-specific insights
    sources = historical_data["sentiment_by_source"].keys()
    for source in sources:
        trend = historical_data.get("comparison", {}).get("sentiment_trend", {}).get(source, {})
        
        if trend:
            direction = trend.get("direction", "")
            strength = trend.get("strength", 0)
            
            if strength > 0.3 and direction:
                insights.append(
                    f"{source.replace('_', ' ').title()} sentiment was {direction} leading up to the event."
                )
    
    # Analyze discrepancies between sources
    source_scores = {}
    for source, data in historical_data["last_day_sentiment"].items():
        source_scores[source] = data["sentiment_score"]
    
    if len(source_scores) >= 2:
        max_source = max(source_scores.items(), key=lambda x: x[1])
        min_source = min(source_scores.items(), key=lambda x: x[1])
        
        if max_source[1] - min_source[1] > 0.4:
            insights.append(
                f"Significant sentiment divergence between sources: {max_source[0].replace('_', ' ').title()} was more bullish than {min_source[0].replace('_', ' ').title()}."
            )
    
    # Add volume insights
    agg_sentiment = historical_data["aggregate_sentiment"]
    if agg_sentiment["total_volume"] > 1000:
        insights.append(
            f"High sentiment volume ({agg_sentiment['total_volume']} mentions) indicates significant market attention."
        )
    
    return insights


def add_sentiment_comparison_to_analysis(event_analysis: Dict) -> Dict:
    """
    Add sentiment comparison data to a historical event analysis.
    
    Args:
        event_analysis: Dictionary containing historical event analysis
        
    Returns:
        Updated analysis with sentiment comparison
    """
    # Only proceed if we have a successful analysis
    if not event_analysis.get("success", False):
        return event_analysis
    
    # Extract the required data
    ticker = event_analysis.get("ticker", "SPY")
    event_date = event_analysis.get("event_date", None)
    
    # Determine sentiment from the analysis trend
    trend = event_analysis.get("trend", "Neutral")
    if trend == "Bullish":
        classified_sentiment = "Bullish"
    elif trend == "Bearish":
        classified_sentiment = "Bearish"
    else:
        classified_sentiment = "Neutral"
    
    # Skip if no event date
    if not event_date:
        return event_analysis
    
    # Get sentiment comparison
    sentiment_comparison = compare_sentiment(classified_sentiment, ticker, event_date)
    
    # Add to the analysis if successful
    if sentiment_comparison.get("success", False):
        event_analysis["sentiment_analysis"] = {
            "classified_sentiment": sentiment_comparison["classified_sentiment"],
            "historical_sentiment": sentiment_comparison["historical_sentiment"],
            "comparison": sentiment_comparison["comparison"],
            "insights": sentiment_comparison["insights"]
        }
    
    return event_analysis


if __name__ == "__main__":
    # Example usage
    ticker = "BTC-USD"
    event_date = "2023-01-21"
    classified_sentiment = "Bullish"
    
    # Get comparison
    comparison = compare_sentiment(classified_sentiment, ticker, event_date)
    
    # Print results
    print(f"\nSentiment Comparison for {ticker} on {event_date}:")
    print(f"Classified: {comparison['classified_sentiment']['label']} " + 
          f"(score: {comparison['classified_sentiment']['score']})")
    print(f"Historical: {comparison['historical_sentiment']['label']} " + 
          f"(score: {comparison['historical_sentiment']['score']})")
    print(f"Agreement: {comparison['comparison']['agreement_label']} " + 
          f"({comparison['comparison']['agreement']})")
    
    print("\nInsights:")
    for i, insight in enumerate(comparison['insights'], 1):
        print(f"{i}. {insight}")
    
    # Example of adding to historical analysis
    sample_analysis = {
        "success": True,
        "ticker": ticker,
        "event_date": event_date,
        "trend": "Bullish",
        "price_change_pct": 5.2
    }
    
    enhanced_analysis = add_sentiment_comparison_to_analysis(sample_analysis)
    print("\nEnhanced Analysis with Sentiment Comparison:")
    print(json.dumps(enhanced_analysis, indent=2)) 