# Financial News Pipeline

This project consists of modules to fetch, classify, and analyze financial news headlines from various sources, match them to historical events, and generate options trade recommendations.

## Modules

### 1. RSS Ingestor (`rss_ingestor.py`)

Fetches and parses real-time headlines from various financial RSS feeds:
- Yahoo Finance (S&P 500 relevant headlines)
- CNBC Markets (Market-moving headlines)
- Reuters Business (Macro + policy + company news)
- Financial Times World (Global events + politics)
- Bloomberg (via RSS aggregator)

### 2. LLM Event Classifier (`llm_event_classifier.py`)

Uses OpenAI (or a local dummy classifier) to classify financial headlines by:
- Event Type (e.g., Inflation, Monetary Policy, Economic Growth)
- Sentiment (Bullish, Bearish, Neutral)
- Sector Impact (Technology, Financials, Energy, etc.)

### 3. Historical Matcher (`historical_matcher.py`)

Matches classified headlines to similar historical events and analyzes market reactions:
- Uses templates of past financial events stored in `historical_event_templates.json`
- Matches new headlines based on event type, sentiment, and sector
- Analyzes post-event market movements using yfinance data
- Returns similar historical events with drop percentages and match scores

### 4. Trade Picker (`trade_picker.py`)

Generates actionable options trade ideas based on headline classifications and historical patterns:
- Selects the most promising trades based on historical market reactions
- Fetches real-time option chain data using yfinance
- Recommends specific option contracts (ticker, strike, expiry)
- Provides detailed rationale for each trade recommendation
- Automatically adjusts strike prices based on historical volatility

### 5. Trade Persistence (`trade_persistence.py`)

Stores and manages trade recommendations for later analysis:
- Saves complete trade data including source headline, similar events, and generated trade
- Allows for loading historical trade recommendations
- Creates a structured trade history for later analysis

### 6. Pipeline Tools

#### Full Pipeline Test (`test_pipeline.py`)

Integrates all components to test the full macro event pipeline:
- Fetches real-time headlines from RSS feeds
- Classifies headlines using the LLM classifier
- Finds similar historical events and their market impacts
- Generates trade recommendations
- Persists trade data to storage
- Reports detailed results at each stage of the pipeline
- Can be run in verbose or quiet mode for different output formats

#### LLM Test (`test_llm.py`)

Bypasses RSS feeds and tests the classification, historical matching, and trade generation with custom headlines:
- Verifies that the LLM classifier is working correctly
- Tests the full pipeline with user-provided custom headlines
- Can optionally save generated trades to storage

#### Trade Viewer (`view_trades.py`)

Utility for viewing and analyzing saved trades:
- View all saved trades or filter by various criteria
- Generate statistics on trades by ticker, option type, event type, etc.
- Command-line interface with support for filters and formatting options

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Running the Full Pipeline

```bash
# Run with detailed verbose output
python test_pipeline.py

# Run with JSON output only
python test_pipeline.py --quiet

# Run without saving trades
python test_pipeline.py --no-save
```

### Testing with Custom Headlines

```bash
# Test classification only
python test_llm.py "Your headline here"

# Test full pipeline including historical matching and trade generation
python test_llm.py --full "Your headline here"

# Test full pipeline and save the generated trade to storage
python test_llm.py --full --save "Your headline here"
```

### Viewing Saved Trades

```bash
# View all saved trades
python view_trades.py view

# View statistics about saved trades
python view_trades.py stats

# Filter trades by criteria
python view_trades.py view --ticker SPY
python view_trades.py view --option CALL
python view_trades.py view --event "Monetary Policy"
python view_trades.py view --sentiment Bearish
python view_trades.py view --sector Technology
```

## OpenAI API Key Management

The project requires an OpenAI API key to function properly. To set up your API key:

1. Create a `.env` file in the root directory (or copy `.env.example` to `.env`)
2. Add your OpenAI API key to the `.env` file:
   ```
   OPENAI_API_KEY=your_api_key_here
   ```

### Security Considerations

- The `.env` file is excluded from version control via `.gitignore` to prevent accidental exposure of your API key
- Never commit your API key to the repository
- Do not share your API key with others
- Consider using environment variables in production environments
- Update your API key if you suspect it has been compromised

### Implementation Details

The application loads the API key using the following methods:
1. Direct reading from the `.env` file
2. Fallback to environment variables if direct reading fails
3. Validation before using the key to prevent errors
4. Proper error messages if the key is missing or invalid

## Output Format

After running the complete pipeline, a trade recommendation will include:

```json
{
    "ticker": "SPY",
    "option_type": "PUT",
    "strike": 510,
    "expiry": "2025-04-19",
    "rationale": "Event similar to 2022-06-15 rate hike which caused -5.6% drop. Matching sentiment and sector suggest downside risk."
}
```

## Trade Persistence

All generated trades are saved to the `trade_history` directory in JSON format for later retrieval and analysis. The trade records include:

- Timestamp of trade generation
- Original headline data (title, source, publication date)
- Classification data (event type, sentiment, sector)
- Similar historical events with match scores
- Generated trade details (ticker, option type, strike, expiry, rationale)

## Project Status

This project is fully functional with all major components implemented:
- ✅ RSS Headline Ingestion
- ✅ LLM-based Event Classification
- ✅ Historical Event Matching
- ✅ Trade Recommendation
- ✅ Trade Persistence and Analysis

Future improvements may include:
- Backtesting framework for trade performance evaluation
- Web interface for monitoring trades
- Email/notification system for new trade alerts
- Integration with trading platforms for automated execution

# Trade Evaluation Process

This section describes how to run the trade evaluation process to assess the performance of the pipeline and generate data for reinforcement learning.

## Weekly Evaluation Process

The `evaluation_runner.py` script is designed to evaluate the performance of trade recommendations after a set period. Running this process weekly provides valuable feedback on the accuracy of your trade predictions and helps improve the system over time.

### Running the Evaluation

```bash
# Basic evaluation of all unevaluated trades
python evaluation_runner.py

# Force re-evaluation of all trades (even previously evaluated ones)
python evaluation_runner.py --force

# Evaluate with a custom number of trading days
python evaluation_runner.py --days 10

# Specify custom input/output files
python evaluation_runner.py --input custom_trades.json --output custom_evaluated.json

# Show detailed output during processing
python evaluation_runner.py --verbose
```

### Setting Up Weekly Automation

#### On Windows (Task Scheduler):

1. Open Task Scheduler
2. Create a Basic Task
   - Name: "Weekly Trade Evaluation"
   - Trigger: Weekly (choose your preferred day)
   - Action: Start a program
   - Program/script: `python` or path to your Python executable
   - Arguments: `evaluation_runner.py --verbose`
   - Start in: Your project directory path

#### On Linux/Mac (Cron):

Add a weekly cron job:

```bash
# Edit crontab
crontab -e

# Add this line to run every Monday at 8:00 AM
0 8 * * 1 cd /path/to/project && python evaluation_runner.py --verbose >> evaluation.log 2>&1
```

### Evaluation Output

The evaluation process:
1. Loads trades from `trade_history.json`
2. Retrieves market data for the specified evaluation period
3. Evaluates the performance of each trade recommendation
4. Calculates metrics like success rate and average price movement
5. Saves evaluated trades to `evaluated_trades.json`
6. Prints a summary of evaluation results

Example summary output:
```
============================================================
TRADE EVALUATION SUMMARY
============================================================
Total trades evaluated: 24
Overall success rate: 62.5%
Average price movement: 3.2%
CALL trades: 14 (71.4% successful)
PUT trades: 10 (50.0% successful)
============================================================

Most recent trade evaluations:
- AAPL CALL: 2.4% move, +
- TSLA PUT: -5.1% move, +
- SPY CALL: 0.8% move, -
- NVDA CALL: 4.3% move, +
- MSFT PUT: 1.2% move, -
```

### Using Evaluation Data for Reinforcement Learning

The evaluated trade data can be used to:
1. Identify patterns in successful vs. unsuccessful trades
2. Adjust matching algorithms based on performance
3. Refine trade selection criteria
4. Train ML models to improve future predictions

By running this evaluation process weekly, you'll build a valuable dataset that reveals strengths and weaknesses in your pipeline's predictions, allowing for continuous improvement of the system.

# Event Analyzer

This program allows you to analyze historical market events by querying an event and comparing stored data with actual market price movements.

## Installation

Make sure you have the required dependencies:

```bash
pip install yfinance pandas
```

## Usage

### List all available events:

```bash
python event_analyzer.py --list
```

### Analyze a specific event:

```bash
python event_analyzer.py "fed rate cut"
```

This will search for events matching the query "fed rate cut" and display the analysis of the best match.

### Customize analysis period:

By default, the analysis looks at 7 trading days following the event. You can customize this:

```bash
python event_analyzer.py "Ukraine" --days 10
```

### Interactive Mode:

For multiple queries without restarting the program, use interactive mode:

```bash
python event_analyzer.py -i
# or
python event_analyzer.py --interactive
```

In interactive mode, you can:
- Type `list` to see all available events
- Enter a query to search for events
- Enter a number to select an event directly from the list
- Use `days [number]` to change the analysis period
- Type `exit` to quit

## Features

- Searches for events based on keywords in event summaries, types, sectors, or sentiments
- Calculates actual price movement and maximum drawdown for the specified ticker
- Compares calculated values with expected values from the template
- Shows daily price movements during the analysis period
- Handles cryptocurrency tickers
- Interactive mode for multiple queries

## Example Output

```
Found event: Fed announces emergency rate cut during COVID-19

Event Analysis Results:
================================================================================
Event: Fed announces emergency rate cut during COVID-19
Date: 2020-03-03
Ticker: SPY
Analysis Period: 2020-03-03 to 2020-03-11 (7 trading days)
--------------------------------------------------------------------------------
Start Price: $308.46
End Price: $275.43
Lowest Price: $267.42
Highest Price: $313.00
--------------------------------------------------------------------------------
Calculated Price Change: -10.71%
Calculated Max Drawdown: -13.29%
Template Price Change: -8.62%
Template Max Drawdown: -7.34%
================================================================================

Daily Closing Prices:
------------------------------------------------------------
2020-03-03: $308.46 (+0.00%)
2020-03-04: $313.00 (+1.47%)
2020-03-05: $302.48 (-1.94%)
2020-03-06: $297.32 (-3.61%)
2020-03-09: $274.95 (-10.86%)
2020-03-10: $283.71 (-8.02%)
2020-03-11: $275.43 (-10.71%)
```

# LLM Event Query

This program allows you to query an LLM (Large Language Model) about a historical market event and then validates the model's answer against actual market data.

## Installation

Make sure you have the required dependencies:

```bash
pip install yfinance pandas openai
```

You'll also need to set your OpenAI API key as an environment variable:

```bash
# Linux/Mac
export OPENAI_API_KEY=your_api_key_here

# Windows PowerShell
$env:OPENAI_API_KEY="your_api_key_here"
```

## Usage

### Query the LLM about an event:

```bash
python llm_event_query.py "What happened when Bitcoin ETF got approved?"
```

### Customize the analysis period:

```bash
python llm_event_query.py "What happened to Apple stock after iPhone 14 launch?" --days 10
```

### Use a different OpenAI model:

```bash
python llm_event_query.py "What happened when SVB collapsed?" --model gpt-4o
```

### Use dummy mode (no API key required):

The program includes a dummy mode that uses predefined responses instead of calling the OpenAI API. This is useful for testing or when you don't have an API key available:

```bash
python llm_event_query.py "What happened when Bitcoin ETF got approved?" --dummy
```

Dummy mode includes predefined responses for the following topics:
- Bitcoin ETF approval
- SVB collapse
- Fed emergency rate cut
- Russia's invasion of Ukraine
- COVID-19 market crash
- Apple iPhone 14 announcement

## Features

- Uses an LLM to identify historical market events and their details
- Validates the LLM's estimations against actual market data
- Shows side-by-side comparison of estimated vs. actual price changes
- Displays daily price movements for deeper analysis
- Works with stocks, ETFs, and cryptocurrencies
- Includes dummy mode for testing without an API key

## Example Output

```
Querying LLM about: "What happened when Bitcoin ETF got approved?"

LLM identified event: Bitcoin ETF approval by SEC on 2024-01-10
Analyzing market data for BTC-USD...

📊 LLM Event Validation Results 📊
================================================================================
Event: Bitcoin ETF approval by SEC
Date: 2024-01-10
Ticker: BTC-USD
Analysis Period: 2024-01-10 to 2024-01-19 (7 trading days)
--------------------------------------------------------------------------------
Start Price: $45941.00
End Price: $41569.00
Lowest Price: $40571.00
Highest Price: $48234.00
--------------------------------------------------------------------------------
📈 LLM Estimate vs. Actual Market Data:
Price Change: 5.00% (LLM) vs -9.52% (Actual)
Max Drawdown: -3.50% (LLM) vs -15.67% (Actual)
--------------------------------------------------------------------------------
LLM Analysis:
The SEC approved spot Bitcoin ETFs on January 10, 2024, allowing direct investment in Bitcoin through traditional brokerage accounts. This was a historic moment for crypto adoption, expected to bring institutional investment and mainstream acceptance. Initially, Bitcoin price spiked to over $48,000 on anticipation, but there was a "sell the news" reaction afterward.
================================================================================

Daily Closing Prices:
------------------------------------------------------------
2024-01-10: $45941.00 (+0.00%)
2024-01-11: $46376.00 (+0.95%)
2024-01-12: $42493.00 (-7.50%)
2024-01-13: $42839.00 (-6.75%)
2024-01-14: $42439.00 (-7.62%)
2024-01-15: $42713.00 (-7.03%)
2024-01-16: $41569.00 (-9.52%)
```

# Ooptions - Financial Market Event Analysis System

A comprehensive system for analyzing financial news headlines, classifying market events, matching them to historical patterns, generating trading recommendations based on macro data and event analysis, and evaluating trade performance.

## New Feature: Analysis Persistence

The system now includes functionality to save historical event analyses and similar events analyses for future reference. This allows you to build a library of analyses that can be searched, viewed, and exported.

### Key Features:

- **Automatic Saving**: Analyses are automatically saved and organized by ticker and event type
- **Query History**: Every query with successful results is recorded for future reference
- **Search & Filter**: Find historical analyses by ticker, date range, or pattern
- **Detailed Viewing**: View complete analyses with all details in text or JSON format
- **Export/Import**: Export analyses for sharing or backup, import them later
- **Command-line Interface**: Easy-to-use CLI for managing your analysis library

### Usage:

Analyses are saved automatically when you run the event query tool:

```bash
# Save analysis results (default behavior)
python llm_event_query.py "What happened when Bitcoin ETF was approved?"

# Skip saving analysis results
python llm_event_query.py --no-save "What happened when Bitcoin ETF was approved?"

# Export analysis to a specific file
python llm_event_query.py --export analysis.json "What happened when Bitcoin ETF was approved?"
```

### Managing Saved Analyses:

Use the `view_analysis.py` tool to manage your saved analyses:

```bash
# List recent analyses
python view_analysis.py list

# Filter by ticker
python view_analysis.py list --ticker BTC-USD

# View detailed information
python view_analysis.py list --detailed

# Show a specific analysis
python view_analysis.py show path/to/analysis_file.json

# Show analysis in JSON format
python view_analysis.py show path/to/analysis_file.json --format json

# Export analyses to a file
python view_analysis.py export export_file.json --ticker AAPL

# View statistics about stored analyses
python view_analysis.py stats

# View query history
python view_analysis.py history

# Search query history
python view_analysis.py history --search "Bitcoin"
```

## New Feature: Sentiment Analysis Integration

The system now includes sentiment analysis functionality that compares our classifier's sentiment prediction with historical sentiment data from news, social media, and analyst ratings. This provides additional context about how the market's sentiment aligns with the actual price movement.

### Key Features:

- **Sentiment Comparison**: Compares price-based sentiment classification with historical sentiment data from multiple sources
- **Source-specific Analysis**: Breaks down sentiment by source (news, social media, analyst ratings) with appropriate weighting
- **Trend Analysis**: Analyzes sentiment trends leading up to an event to identify shifting market sentiment
- **Performance Correlation**: Evaluates how sentiment alignment correlates with market performance
- **Insights Generation**: Automatically generates insights about sentiment patterns and divergences

### Usage:

When analyzing a historical event, the system now automatically includes sentiment analysis in the results:

```
📊 SENTIMENT ANALYSIS COMPARISON:
Price-Based Sentiment: Bullish (score: 0.4)
Historical Sentiment: Very Bullish (score: 0.72)
Agreement: Strong Agreement (0.75)

Sentiment Insights:
  • Your classification (Bullish) partially aligns with historical sentiment data (Very Bullish).
  • Social Media sentiment was improving leading up to the event.
  • High sentiment volume (1250 mentions) indicates significant market attention.
```

For similar events analysis, sentiment patterns across multiple events are analyzed:

```
🔍 SENTIMENT PATTERN ANALYSIS:
Events with sentiment data: 5
Sentiment-price alignment: 80% of events

Performance when sentiment aligned with price: 6.5% (4 events)
Performance when sentiment diverged from price: 2.1% (1 events)

Sentiment Pattern Insights:
  1. Events where sentiment analysis aligned with historical sentiment had stronger price movements (6.5% vs 2.1%)
  2. Strong consistency (80%) between price-based classification and historical sentiment data suggests reliable sentiment signals for these events
```

## Getting Started

### Installation

```bash
pip install -r requirements.txt
```

### Basic Usage

```bash
python llm_event_query.py "What happened to Bitcoin when the ETF was approved?"
```

### Testing Sentiment Analysis

```bash
python test_sentiment.py
```

## Configuration

Sentiment analysis is automatically included in event analysis. The main parameters are:

- `DEFAULT_LOOKBACK_DAYS`: Number of days to analyze sentiment before an event (default: 30)
- `DEFAULT_SENTIMENT_SOURCES`: Sources to include in sentiment analysis (default: news, social media, analyst ratings)

## Dependencies

- pandas
- numpy
- requests
- openai
- yfinance
- fredapi

## License

MIT 