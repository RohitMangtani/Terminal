import openai
import json
import time
import os
import datetime
from typing import List, Dict, Any, Optional, Literal
from rss_ingestor import fetch_rss_headlines
from macro_data_collector import get_macro_snapshot, get_fred_data
from options_data_collector import get_options_snapshot
from event_tagger import generate_event_tags
from prompt_context_builder import build_prompt_context
import argparse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Toggle between OpenAI API and a local dummy classifier for testing
MODEL_TYPE: Literal["openai", "dummy"] = "openai"

# OpenAI API configuration
# Read API key directly from .env file to ensure we get the current value
try:
    with open('.env', 'r') as f:
        env_contents = f.read()
        for line in env_contents.splitlines():
            if line.startswith('OPENAI_API_KEY='):
                OPENAI_API_KEY = line.split('=', 1)[1]
                if OPENAI_API_KEY and len(OPENAI_API_KEY) > 20:  # Simple validation for key length
                    print(f"✅ OpenAI API key loaded directly from .env file: {OPENAI_API_KEY[:4]}...{OPENAI_API_KEY[-4:]}")
                else:
                    print("⚠️ WARNING: OpenAI API key found but appears to be invalid")
                    OPENAI_API_KEY = None
                break
        else:
            OPENAI_API_KEY = None
            print("❌ ERROR: OPENAI_API_KEY not found in .env file")
except Exception as e:
    print(f"❌ ERROR reading .env file: {str(e)}")
    OPENAI_API_KEY = None

# Fallback to environment variable if direct read failed
if not OPENAI_API_KEY:
    API_KEY_FROM_ENV = os.getenv('OPENAI_API_KEY')
    if API_KEY_FROM_ENV and len(API_KEY_FROM_ENV) > 20:  # Simple validation
        OPENAI_API_KEY = API_KEY_FROM_ENV
        print(f"✅ OpenAI API key loaded from environment variable: {OPENAI_API_KEY[:4]}...{OPENAI_API_KEY[-4:]}")
    else:
        print("❌ ERROR: OpenAI API key not found in environment or appears invalid")
        print("⚠️ The application will continue but some features may be limited")
        # We'll set this to continue but API calls will fail
        OPENAI_API_KEY = "temporarily_unavailable"

DEFAULT_MODEL = os.getenv('OPENAI_MODEL', "gpt-3.5-turbo")

# Rate limiting parameters
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

# Include macro and options data in classification
USE_MACRO_CONTEXT = True
USE_OPTIONS_CONTEXT = True

class DummyClassifier:
    """A simple dummy classifier for testing without API calls."""
    
    def classify(self, headline: Dict[str, Any], provided_macro_context: Dict[str, Any] = None) -> Dict[str, str]:
        """
        Simple rule-based classification based on keywords in headline text.
        This is only for testing/fallback and not meant to be accurate.
        Now includes dummy trade recommendations to match the enhanced format.
        """
        title = headline.get("title", "").lower()
        
        # Get macro context if enabled (for consistency with OpenAIClassifier)
        # Note: Dummy classifier doesn't actually use this data
        if USE_MACRO_CONTEXT:
            if provided_macro_context:
                # Just log that we got the context, but don't use it
                print(f"Dummy classifier received {len(provided_macro_context)} macro indicators (not used)")
            else:
                try:
                    _ = get_macro_snapshot(use_cache=True)
                    # We just fetch it but don't use it to keep the dummy classifier simple
                except Exception as e:
                    print(f"Error fetching macro context in dummy classifier: {str(e)}")
        
        # Default classification
        classification = {
            "event_type": "Other",
            "sentiment": "Neutral",
            "sector": "General"
        }
        
        # Simple keyword-based rules for event type
        if any(word in title for word in ["fed", "rate", "interest", "powell", "central bank", "monetary"]):
            classification["event_type"] = "Monetary Policy"
        elif any(word in title for word in ["inflation", "cpi", "prices", "cost"]):
            classification["event_type"] = "Inflation"
        elif any(word in title for word in ["gdp", "growth", "economy", "recession"]):
            classification["event_type"] = "Economic Growth"
        elif any(word in title for word in ["trade", "tariff", "export", "import"]):
            classification["event_type"] = "Trade"
        elif any(word in title for word in ["war", "conflict", "military", "attack", "defense"]):
            classification["event_type"] = "Geopolitical"
        elif any(word in title for word in ["tax", "budget", "spending", "fiscal"]):
            classification["event_type"] = "Fiscal Policy"
        elif any(word in title for word in ["regulation", "compliance", "law", "legislation"]):
            classification["event_type"] = "Regulation"
        
        # Simple keyword-based rules for sentiment
        if any(word in title for word in ["up", "rise", "gain", "positive", "rally", "surge", "grow", "bullish"]):
            classification["sentiment"] = "Bullish"
        elif any(word in title for word in ["down", "fall", "drop", "negative", "decline", "bearish", "crash", "fear"]):
            classification["sentiment"] = "Bearish"
        
        # Simple keyword-based rules for sector
        if any(word in title for word in ["tech", "software", "ai", "digital", "chip", "semiconductor"]):
            classification["sector"] = "Technology"
        elif any(word in title for word in ["bank", "finance", "mortgage", "loan", "credit", "insurance"]):
            classification["sector"] = "Financials"
        elif any(word in title for word in ["oil", "gas", "renewable", "solar", "energy", "power"]):
            classification["sector"] = "Energy"
        elif any(word in title for word in ["retail", "consumer", "shop", "store", "spending"]):
            classification["sector"] = "Consumer"
        elif any(word in title for word in ["health", "biotech", "pharma", "medical", "healthcare"]):
            classification["sector"] = "Healthcare"
        
        # Determine ticker for the dummy classifier
        ticker = "SPY"  # Default ticker
        
        # Look for capitalized words that could be tickers
        words = headline.get("title", "").split()
        ticker_candidates = []
        for word in words:
            # Check if word is all uppercase and 1-5 characters
            if word.isupper() and 1 <= len(word) <= 5 and word.isalpha():
                ticker_candidates.append(word)
        
        # Use the first candidate if any found
        if ticker_candidates:
            ticker = ticker_candidates[0]
        
        # Generate event tags for the headline (even in dummy classifier)
        event_date = datetime.datetime.now()
        try:
            event_tags = generate_event_tags(headline.get("title", ""), provided_macro_context, event_date, ticker)
            print(f"Dummy classifier generated event tags: {event_tags}")
            classification["event_tags"] = event_tags
            
            # Generate prompt enhancers with build_prompt_context (even though dummy classifier doesn't use it)
            # This is for consistency with OpenAIClassifier
            prompt_enhancers = build_prompt_context(event_date, provided_macro_context, event_tags)
            print(f"Dummy classifier generated prompt enhancers (not used): {prompt_enhancers.keys()}")
        except Exception as e:
            print(f"Error generating event tags in dummy classifier: {str(e)}")
            # Create default event tags if generation fails
            classification["event_tags"] = {
                "surprise_positive": False,
                "is_fed_week": False,
                "is_cpi_week": False,
                "is_earnings_season": False,
                "is_repeat_event": False
            }
        
        # Add dummy trade recommendation based on sentiment and sector
        option_type = "CALL" if classification["sentiment"] == "Bullish" else "PUT"
        
        # Assign sector-specific tickers when available
        if classification["sector"] == "Technology":
            ticker = "QQQ"
        elif classification["sector"] == "Financials":
            ticker = "XLF"
        elif classification["sector"] == "Energy":
            ticker = "XLE"
        elif classification["sector"] == "Healthcare":
            ticker = "XLV"
        elif classification["sector"] == "Consumer":
            ticker = "XLP"
        
        # Fetch options data if enabled (just for consistency with OpenAIClassifier)
        if USE_OPTIONS_CONTEXT:
            try:
                _ = get_options_snapshot(ticker, use_cache=True)
                # Just fetch it but don't use it for the dummy classifier
            except Exception as e:
                print(f"Error fetching options data in dummy classifier: {str(e)}")
        
        # Add dummy trade information
        classification["trade"] = {
            "ticker": ticker,
            "option_type": option_type,
            "strike": "ATM",  # At-the-money
            "expiry": "30d",  # 30 days out
            "rationale": f"Dummy recommendation based on {classification['sentiment']} sentiment for {classification['sector']} sector"
        }
        
        return classification

class OpenAIClassifier:
    """Uses OpenAI API to classify financial headlines."""
    
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        if not api_key or api_key == "your_new_openai_api_key_here":
            raise ValueError("Invalid API key provided to OpenAIClassifier")
        
        self.api_key = api_key
        self.model = model
        # Set API key
        openai.api_key = api_key
        print(f"OpenAI API key set successfully: {api_key[:4]}...{api_key[-4:]}")
    
    def classify(self, headline: Dict[str, Any], provided_macro_context: Dict[str, Any] = None) -> Dict[str, str]:
        """
        Use OpenAI API to classify the headline by event type, sentiment, sector, and recommend trades.
        
        When USE_MACRO_CONTEXT is enabled, the classifier incorporates current
        macroeconomic data (CPI, Fed Funds Rate, VIX, yield curve, etc.) to provide
        more contextualized classification and trade recommendations.
        
        When USE_OPTIONS_CONTEXT is enabled, the classifier incorporates current
        options market data (IV, skew, put/call ratio, OI) to provide more informed
        trade recommendations.
        
        Args:
            headline: A dictionary containing headline information
            provided_macro_context: Optional pre-fetched macroeconomic data
            
        Returns:
            Dictionary with classification results including:
            - event_type: Type of macroeconomic event
            - sentiment: Market sentiment implied (Bullish, Bearish, Neutral)
            - sector: Primary sector impacted by the event
            - trade: Recommended options trade (if applicable)
        """
        title = headline.get("title", "")
        summary = headline.get("summary", "")
        source = headline.get("source", "")
        
        # Get macro context if enabled
        macro_context = None
        if USE_MACRO_CONTEXT:
            # Use provided macro context if available
            if provided_macro_context:
                macro_context = provided_macro_context
                print(f"Using provided FRED macro data with {len(macro_context)} indicators")
            else:
                try:
                    macro_context = get_macro_snapshot(use_cache=True)
                    # Remove metadata fields that start with _
                    macro_context = {k: v for k, v in macro_context.items() if not k.startswith('_')}
                except Exception as e:
                    print(f"Error fetching macro context: {str(e)}")
        
        # Determine ticker for options data (default to SPY)
        # First try to extract ticker from headline, otherwise use default
        ticker = "SPY"
        ticker_candidates = []
        
        # Look for capitalized words that could be tickers
        words = title.split()
        for word in words:
            # Check if word is all uppercase and 1-5 characters
            if word.isupper() and 1 <= len(word) <= 5 and word.isalpha():
                ticker_candidates.append(word)
        
        # Use the first candidate if any found
        if ticker_candidates:
            ticker = ticker_candidates[0]
        
        # Get options data if enabled
        options_context = None
        if USE_OPTIONS_CONTEXT:
            try:
                options_context = get_options_snapshot(ticker, use_cache=True)
                print(f"Using options data for {ticker}")
            except Exception as e:
                print(f"Error fetching options data for {ticker}: {str(e)}")
        
        # Generate event tags from headline, macro data, and ticker
        event_date = datetime.datetime.now()
        event_tags = generate_event_tags(title, macro_context, event_date, ticker)
        print(f"Generated event tags: {event_tags}")
        
        # Generate enhanced prompt context from event date, macro data, and event tags
        prompt_enhancers = build_prompt_context(event_date, macro_context, event_tags)
        print(f"Generated prompt enhancers: {list(prompt_enhancers.keys())}")
        
        # Initialize retry counter
        retries = 0
        
        while retries < MAX_RETRIES:
            try:
                # Create a properly formatted macro string for OpenAI API
                macro_string = json.dumps(macro_context, indent=2) if macro_context else "No macroeconomic data available"
                
                # Create a properly formatted options string for OpenAI API
                options_string = json.dumps(options_context, indent=2) if options_context else "No options data available"
                
                # Create a properly formatted event tags string for OpenAI API
                event_tags_string = json.dumps(event_tags, indent=2) if event_tags else "No event tags available"
                
                # Format the headline text with all available information
                headline_text = f"{title}"
                if summary:
                    headline_text += f"\nSummary: {summary}"
                if source:
                    headline_text += f"\nSource: {source}"
                
                # Using the specified message format for OpenAI API
                system_message = "You are a macroeconomic and options market classifier. Use macro data, options market indicators, and event tags to guide your reasoning."
                user_message = f"Headline: '{headline_text}'\n\n"
                
                if USE_MACRO_CONTEXT:
                    user_message += f"Macro Context:\n{macro_string}\n\n"
                    # Add enhanced time-aware context
                    user_message += f"🕒 Time Awareness:\n{prompt_enhancers['time_aware_text']}\n\n"
                    # Add enhanced delta description
                    user_message += f"📊 Economic Surprise:\n{prompt_enhancers['delta_description']}\n\n"
                    # Add enhanced relevance weights
                    user_message += f"⚖️ Relevance Signals:\n{prompt_enhancers['relevance_weights']}\n\n"
                    # Add instruction for enhanced context
                    user_message += "Use these to better understand the urgency and magnitude of the event.\n\n"
                
                if USE_OPTIONS_CONTEXT:
                    user_message += f"Options Sentiment Context:\n{options_string}\n\n"
                
                # Include event tags in the prompt with the specific format requested
                user_message += f"Event Feature Tags:\n{event_tags_string}\n\n"
                
                # Add instruction on how to use the event tags
                user_message += "Use these event-specific tags to understand if the headline occurred during a volatile period or surprised the market. Adjust your sentiment and trade recommendation accordingly.\n\n"
                
                user_message += "Based on this data, classify the event and recommend an options trade. "
                user_message += "Consider event tags when making your recommendation. "
                user_message += "If it's a repeat event, check if previous similar events had predictable impacts. "
                user_message += "If it's a Fed week or CPI week, consider the heightened volatility. "
                user_message += "If IV is high and skew is bearish (puts more expensive), favor PUTs. "
                user_message += "If sentiment is bullish with low IV and call skew, favor CALLs. "
                # Add explicit directional instruction
                user_message += "Given this news and macro context, would you BUY or SELL this stock? Justify your directional choice in your recommendation. "
                user_message += "Return JSON in this format: {event_type, sentiment, sector, trade, direction}"
                
                response = openai.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {
                            "role": "system",
                            "content": system_message
                        },
                        {
                            "role": "user",
                            "content": user_message
                        }
                    ],
                    temperature=0.2,
                    response_format={"type": "json_object"}
                )
                
                # Parse the response
                classification_text = response.choices[0].message.content
                classification = json.loads(classification_text)
                
                # Ensure we have all required fields
                required_fields = ["event_type", "sentiment", "sector"]
                if all(key in classification for key in required_fields):
                    result = {
                        "event_type": classification["event_type"],
                        "sentiment": classification["sentiment"],
                        "sector": classification["sector"],
                        "event_tags": event_tags  # Include the event tags in the result
                    }
                    
                    # Extract direction if available
                    if "direction" in classification:
                        result["direction"] = classification["direction"].upper()  # Ensure it's uppercase (BUY/SELL)
                    
                    # Add trade information if available
                    if "trade" in classification:
                        # Handle different possible formats of trade data
                        if isinstance(classification["trade"], dict):
                            result["trade"] = classification["trade"]
                            
                            # Ensure the trade object has all required fields
                            if not all(k in result["trade"] for k in ["ticker", "option_type"]):
                                # Add defaults for missing fields
                                if "ticker" not in result["trade"]:
                                    result["trade"]["ticker"] = ticker
                                if "option_type" not in result["trade"]:
                                    # Infer option type from sentiment if possible
                                    opt_type = "CALL" if result["sentiment"] == "Bullish" else "PUT"
                                    result["trade"]["option_type"] = opt_type
                                if "rationale" not in result["trade"]:
                                    result["trade"]["rationale"] = f"Based on {result['sentiment']} sentiment for {result['sector']} sector"
                            
                            # Add direction to trade object if available at the top level
                            if "direction" in result and "direction" not in result["trade"]:
                                result["trade"]["direction"] = result["direction"]
                        else:
                            # If trade is a string or other format, create a standardized structure
                            trade_info = str(classification["trade"])
                            opt_type = "CALL" if result["sentiment"] == "Bullish" else "PUT"
                            
                            # Determine direction (default based on sentiment if not explicitly provided)
                            direction = result.get("direction", "BUY")
                            if not direction:
                                direction = "BUY" if result["sentiment"] == "Bullish" else "SELL"
                            
                            result["trade"] = {
                                "ticker": ticker,
                                "option_type": opt_type,
                                "strike": "ATM",  # At-the-money
                                "expiry": "30d",  # 30 days out
                                "direction": direction,
                                "trade_type": "option",  # Default to option
                                "rationale": trade_info
                            }
                    
                    return result
                else:
                    missing = [field for field in required_fields if field not in classification]
                    raise ValueError(f"Missing required classification fields: {', '.join(missing)}")
                    
            except Exception as e:
                retries += 1
                if retries >= MAX_RETRIES:
                    print(f"Error classifying headline after {MAX_RETRIES} retries: {str(e)}")
                    # Fall back to dummy classifier
                    dummy_result = DummyClassifier().classify(headline, provided_macro_context)
                    # Add event tags to the dummy result
                    dummy_result["event_tags"] = event_tags
                    return dummy_result
                
                print(f"API error (attempt {retries}/{MAX_RETRIES}): {str(e)}. Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
        
        # If we get here, all retries failed
        dummy_result = DummyClassifier().classify(headline, provided_macro_context)
        # Add event tags to the dummy result
        dummy_result["event_tags"] = event_tags
        return dummy_result

def get_classifier() -> Any:
    """Factory function to get the appropriate classifier based on the model type."""
    if not OPENAI_API_KEY:
        print("❌ ERROR: OpenAI API key is not set or is invalid")
        print("Please set the OPENAI_API_KEY environment variable or add it to the .env file")
        if MODEL_TYPE == "dummy":
            print("Using dummy classifier as fallback")
            return DummyClassifier()
        else:
            raise ValueError("OPENAI_API_KEY environment variable is not set. Cannot proceed without an API key.")
    
    if MODEL_TYPE == "dummy":
        print("WARNING: Using dummy classifier is not recommended for production use.")
        return DummyClassifier()
    
    # Default to OpenAI classifier
    return OpenAIClassifier(api_key=OPENAI_API_KEY)

def classify_macro_event(headline: Dict[str, Any]) -> Dict[str, str]:
    """
    Classify a headline by event type, sentiment, and impacted sector.
    
    When USE_MACRO_CONTEXT is enabled, the classifier will consider current
    macroeconomic indicators when making classifications.
    
    When USE_OPTIONS_CONTEXT is enabled, the classifier will consider current
    options market data when making recommendations.
    
    Args:
        headline: A dictionary containing headline information
        
    Returns:
        Dictionary with classification results
    """
    # Fetch direct FRED data for this specific classification run
    macro_context = get_fred_data()
    
    # Create a properly formatted macro string for debugging
    if macro_context:
        macro_string = json.dumps(macro_context, indent=2)
        # Display a sample of the macro data (first few characters)
        sample_length = 100
        sample = macro_string[:sample_length] + "..." if len(macro_string) > sample_length else macro_string
        print(f"Using macro data for classification (sample): {sample}")
    
    classifier = get_classifier()
    return classifier.classify(headline, provided_macro_context=macro_context)

def classify_all_headlines(headlines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Process multiple headlines and add classification data to each.
    
    When USE_MACRO_CONTEXT is enabled, macroeconomic indicators are fetched once
    and used for all headlines in the batch to reduce API calls.
    
    When USE_OPTIONS_CONTEXT is enabled, options market data is fetched for
    each ticker separately but cached to reduce API calls.
    
    Args:
        headlines: List of headline dictionaries from rss_ingestor
        
    Returns:
        List of headline dictionaries with added classification data
    """
    classifier = get_classifier()
    classified_headlines = []
    
    # Fetch FRED data once for all headlines
    macro_context = None
    if USE_MACRO_CONTEXT:
        try:
            macro_context = get_fred_data()
            # Format for easier debugging
            macro_string = json.dumps(macro_context, indent=2)
            print(f"Fetched {len(macro_context)} macro indicators from FRED for batch classification")
            print(f"Sample macro data (first 3 indicators):")
            for i, (key, value) in enumerate(macro_context.items()):
                if i < 3:
                    print(f"  {key}: {value}")
                else:
                    break
        except Exception as e:
            print(f"Error fetching FRED data for batch classification: {str(e)}")
    
    # For options data, we'll use the cache mechanism built into get_options_snapshot
    # since different headlines might need different tickers
    
    for headline in headlines:
        # Classify the headline
        classification = classifier.classify(headline, provided_macro_context=macro_context)
        
        # Create a new dictionary with all original data plus classification
        classified_headline = headline.copy()
        classified_headline.update(classification)
        
        classified_headlines.append(classified_headline)
        
        # Add a small delay between API calls to avoid rate limiting
        if MODEL_TYPE == "openai" and OPENAI_API_KEY:
            time.sleep(0.5)
    
    return classified_headlines

if __name__ == "__main__":
    # Add command line arguments for testing
    parser = argparse.ArgumentParser(description="Test the financial headline classifier")
    parser.add_argument("--no-macro", action="store_true", help="Disable macro context in classification")
    parser.add_argument("--no-options", action="store_true", help="Disable options context in classification")
    parser.add_argument("--count", type=int, default=3, help="Number of headlines to classify")
    args = parser.parse_args()
    
    # Override context flags if specified in arguments
    if args.no_macro:
        USE_MACRO_CONTEXT = False
        print("Macro context disabled for testing")
    else:
        print("Using macro context in classification")
    
    if args.no_options:
        USE_OPTIONS_CONTEXT = False
        print("Options context disabled for testing")
    else:
        print("Using options context in classification")
    
    # Test the classifier with some headlines
    headlines = fetch_rss_headlines()
    
    if headlines:
        # Just classify the first few headlines to demo
        test_headlines = headlines[:args.count]
        classified_headlines = classify_all_headlines(test_headlines)
        
        # Print the results
        for headline in classified_headlines:
            print(f"Title: {headline['title']}")
            print(f"Source: {headline['source']}")
            print(f"Event Type: {headline['event_type']}")
            print(f"Sentiment: {headline['sentiment']}")
            print(f"Sector: {headline['sector']}")
            
            # Print event tags if available
            if "event_tags" in headline and isinstance(headline["event_tags"], dict):
                print("\nEvent Tags:")
                for tag, value in headline["event_tags"].items():
                    print(f"  {tag}: {value}")
            
            # Print trade recommendation if available
            if "trade" in headline and isinstance(headline["trade"], dict):
                trade = headline["trade"]
                print("\nTrade Recommendation:")
                print(f"  Ticker: {trade.get('ticker', 'N/A')}")
                print(f"  Option: {trade.get('option_type', 'N/A')}")
                print(f"  Strike: {trade.get('strike', 'N/A')}")
                print(f"  Expiry: {trade.get('expiry', 'N/A')}")
                print(f"  Rationale: {trade.get('rationale', 'N/A')}")
            
            print("-" * 50)
    else:
        print("No headlines fetched from RSS feeds.") 