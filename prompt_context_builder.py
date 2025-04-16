#!/usr/bin/env python
"""
PROMPT CONTEXT BUILDER MODULE
============================

What This Module Does:
--------------------
This module builds enhanced contextual information for LLM prompts by analyzing
macroeconomic data and event tags. It helps provide the LLM with richer, more
nuanced information about market conditions, recent changes, and the relevance
of different economic indicators.

How to Use:
----------
1. Generate enhanced prompt context:
   from prompt_context_builder import build_prompt_context
   context = build_prompt_context(event_date, macro_snapshot, event_tags)

2. Use the returned context in your LLM prompts:
   prompt += f"Time context: {context['time_aware_text']}\n"
   prompt += f"Recent changes: {context['delta_description']}\n"
   prompt += f"Key indicators: {context['relevance_weights']}\n"

What This Helps You See:
-----------------------
- Provides time-aware context about market conditions
- Highlights recent significant changes in economic indicators
- Identifies which economic metrics are most relevant for the current event
- Creates more nuanced LLM prompts that consider broader market context
"""

import datetime
from typing import Dict, Any, List, Tuple, Optional
import math
import re

# Constants for economic indicators
SIGNIFICANT_DELTA_THRESHOLD = {
    "CPI_YoY": 0.3,  # Significant change in CPI (percentage points)
    "CoreCPI": 0.2,  # Significant change in Core CPI (percentage points)
    "FedFundsRate": 0.25,  # Significant change in Fed Funds Rate (percentage points)
    "Unemployment": 0.2,  # Significant change in unemployment (percentage points)
    "VIX": 5.0,  # Significant change in VIX (points)
    "GDP_QoQ": 0.5,  # Significant change in quarterly GDP (percentage points)
    "Treasury10Y": 0.2,  # Significant change in 10-year yield (percentage points)
    "Treasury2Y": 0.2,  # Significant change in 2-year yield (percentage points)
    "DEFAULT": 0.1  # Default threshold for other metrics (10% change)
}

# Weights for different economic indicators based on event type
EVENT_TYPE_WEIGHTS = {
    "Monetary Policy": {
        "FedFundsRate": 10,
        "Treasury2Y": 8,
        "Treasury10Y": 7,
        "VIX": 5,
        "CPI_YoY": 6,
        "Unemployment": 6
    },
    "Inflation": {
        "CPI_YoY": 10,
        "CoreCPI": 9,
        "FedFundsRate": 7,
        "Treasury2Y": 6, 
        "Treasury10Y": 5
    },
    "Economic Growth": {
        "GDP_QoQ": 10,
        "Unemployment": 8,
        "RetailSales": 7,
        "Treasury10Y": 5
    },
    "Earnings": {
        "VIX": 8,
        "SP500_PE": 7,
        "Treasury10Y": 5,
        "GDP_QoQ": 6
    }
}

# FOMC meeting schedule (from Federal Reserve website)
# Format: List of tuples (year, month, day, is_important)
# is_important indicates meetings with press conferences and updated projections
# NOTE: This is used as a fallback if we can't fetch the actual schedule
FALLBACK_FOMC_SCHEDULE = [
    # 2023 meetings (historical reference)
    (2023, 1, 31, True), (2023, 3, 21, True),
    (2023, 5, 2, True), (2023, 6, 13, True),
    (2023, 7, 25, True), (2023, 9, 19, True),
    (2023, 10, 31, True), (2023, 12, 12, True),
    
    # 2024 meetings
    (2024, 1, 30, True), (2024, 3, 19, True),
    (2024, 5, 1, True), (2024, 6, 11, True),
    (2024, 7, 30, True), (2024, 9, 17, True),
    (2024, 11, 6, True), (2024, 12, 17, True),
    
    # 2025 meetings (projected)
    (2025, 1, 28, True), (2025, 3, 18, True),
    (2025, 4, 29, True), (2025, 6, 10, True),
    (2025, 7, 29, True), (2025, 9, 16, True),
    (2025, 11, 4, True), (2025, 12, 16, True)
]

# Cache for FOMC meetings to avoid repeated API calls
_fomc_cache = None
_fomc_cache_expiry = None
_cpi_cache = None
_cpi_cache_expiry = None
_earnings_cache = None
_earnings_cache_expiry = None

# Economic indicator interpretation thresholds
INDICATOR_INTERPRETATIONS = {
    "CPI_YoY": [
        (5.0, "extremely high inflation", "high risk"),
        (3.0, "high inflation", "medium risk"),
        (2.0, "target inflation", "low risk"),
        (1.0, "below-target inflation", "deflation concern"),
        (0.0, "no inflation", "deflation risk"),
        (-1.0, "deflation", "high risk")
    ],
    "Unemployment": [
        (7.0, "high unemployment", "recession signal"),
        (5.0, "elevated unemployment", "growth concern"),
        (4.0, "moderate unemployment", "neutral"),
        (3.5, "low unemployment", "strong labor market"),
        (3.0, "very low unemployment", "overheating risk")
    ],
    "VIX": [
        (30.0, "extreme volatility", "crisis level"),
        (20.0, "high volatility", "high risk"),
        (15.0, "moderate volatility", "normal market"),
        (10.0, "low volatility", "complacency risk")
    ],
    "Treasury2Y": [
        (5.0, "very high 2Y yield", "tight monetary policy"),
        (3.5, "high 2Y yield", "restrictive policy"),
        (2.0, "moderate 2Y yield", "neutral policy"),
        (1.0, "low 2Y yield", "accommodative policy"),
        (0.5, "very low 2Y yield", "highly accommodative")
    ],
    "FedFundsRate": [
        (5.0, "very high Fed rate", "restrictive policy"),
        (3.5, "high Fed rate", "moderately restrictive"),
        (2.5, "neutral Fed rate", "neutral policy"),
        (1.5, "low Fed rate", "accommodative policy"),
        (0.5, "very low Fed rate", "highly accommodative")
    ],
    "GDP_QoQ": [
        (3.0, "strong growth", "expansion"),
        (2.0, "moderate growth", "normal growth"),
        (1.0, "weak growth", "slowdown concern"),
        (0.0, "no growth", "stagnation"),
        (-1.0, "contraction", "recession signal")
    ]
}

def fetch_fomc_meeting_dates():
    """
    Fetch FOMC meeting dates from external source.
    
    This function attempts to fetch FOMC meeting dates from:
    1. The Federal Reserve website
    2. A reliable financial data API
    3. Falls back to hardcoded dates if neither option works
    
    Returns:
        List of tuples (year, month, day, is_important)
    """
    global _fomc_cache, _fomc_cache_expiry
    
    # Check if we have a valid cache
    current_time = datetime.datetime.now()
    if _fomc_cache and _fomc_cache_expiry and _fomc_cache_expiry > current_time:
        return _fomc_cache
    
    try:
        # Set cache expiry for 24 hours from now (as FOMC schedules don't change often)
        cache_expiry = current_time + datetime.timedelta(hours=24)
        
        # Try to fetch from Federal Reserve website using requests library
        import requests
        from bs4 import BeautifulSoup
        
        # Attempt to scrape from the official Federal Reserve calendar page
        try:
            url = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Initialize list for meeting dates
                fomc_dates = []
                
                # Look for tables containing FOMC schedule
                # The structure of the page has tables with class "calendar-content"
                # First find the current year and future years' tables
                tables = soup.select('div.panel-default')
                
                for table in tables:
                    year_header = table.select_one('div.panel-heading')
                    if not year_header:
                        continue
                    
                    # Extract year from header
                    year_text = year_header.get_text(strip=True)
                    year_match = re.search(r'(\d{4})', year_text)
                    if not year_match:
                        continue
                    
                    year = int(year_match.group(1))
                    
                    # Process each meeting date in this year's table
                    meeting_rows = table.select('tr')
                    for row in meeting_rows:
                        date_cell = row.select_one('td:nth-child(1)')
                        if not date_cell:
                            continue
                        
                        # Extract date information
                        date_text = date_cell.get_text(strip=True)
                        if not date_text:
                            continue
                        
                        # Check if this is a regular meeting and not some other event
                        if "meeting" not in date_text.lower():
                            continue
                        
                        # Parse date (format can vary but often like "January 30-31")
                        date_match = re.search(r'(\w+)\s+(\d+)(?:-\d+)?', date_text)
                        if date_match:
                            month_name, day = date_match.groups()
                            month = datetime.datetime.strptime(month_name, '%B').month
                            day = int(day)
                            
                            # Determine if it's an important meeting (with press conference)
                            # Typically all meetings now have press conferences
                            is_important = True
                            
                            fomc_dates.append((year, month, day, is_important))
                
                # If we successfully found dates, update cache and return
                if fomc_dates:
                    _fomc_cache = fomc_dates
                    _fomc_cache_expiry = cache_expiry
                    return fomc_dates
        
        except Exception as e:
            print(f"Error fetching FOMC dates from Federal Reserve website: {e}")
        
        # If Federal Reserve website scraping fails, try alternative API sources
        # Example: Using a financial data API (placeholder for actual API implementation)
        try:
            # This is a placeholder for an actual API call
            # In a production environment, you would integrate with a financial data provider
            # such as Bloomberg, Refinitiv, Alpha Vantage, etc.
            pass
        except Exception as e:
            print(f"Error fetching FOMC dates from alternative API: {e}")
        
        # If all attempts fail, use fallback hardcoded schedule
        # But filter for dates that are in the future or very recent past
        today = datetime.date.today()
        three_months_ago = today - datetime.timedelta(days=90)
        
        # Filter fallback schedule to only include recent and future dates
        # This ensures we don't return very old meetings even in fallback mode
        filtered_fallback = []
        for year, month, day, is_important in FALLBACK_FOMC_SCHEDULE:
            meeting_date = datetime.date(year, month, day)
            if meeting_date >= three_months_ago:
                filtered_fallback.append((year, month, day, is_important))
        
        _fomc_cache = filtered_fallback
        _fomc_cache_expiry = cache_expiry
        return filtered_fallback
        
    except Exception as e:
        print(f"Error in FOMC date fetching: {e}")
        # Return fallback if there's any unexpected error
        return FALLBACK_FOMC_SCHEDULE

def fetch_cpi_release_dates(year: int = None) -> List[Tuple[int, int, int]]:
    """
    Fetch CPI (Consumer Price Index) release dates from external sources.
    
    This function attempts to fetch CPI release dates from:
    1. The Bureau of Labor Statistics website
    2. A reliable financial data API
    3. Falls back to calculating estimates based on typical release patterns
    
    Args:
        year: Optional year to filter results (defaults to current year if None)
        
    Returns:
        List of tuples (year, month, day)
    """
    global _cpi_cache, _cpi_cache_expiry
    
    # Use current year if not specified
    if year is None:
        year = datetime.datetime.now().year
    
    # Check if we have a valid cache
    current_time = datetime.datetime.now()
    if _cpi_cache and _cpi_cache_expiry and _cpi_cache_expiry > current_time:
        # If we have a cache but need to filter by year
        if year is not None:
            return [date_tuple for date_tuple in _cpi_cache if date_tuple[0] == year]
        return _cpi_cache
    
    try:
        # Set cache expiry for 24 hours
        cache_expiry = current_time + datetime.timedelta(hours=24)
        
        # Try to fetch from BLS website
        import requests
        from bs4 import BeautifulSoup
        
        try:
            # Attempt to get data from BLS
            url = "https://www.bls.gov/schedule/news_release/cpi.htm"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Initialize list for release dates
                cpi_dates = []
                
                # Find the release schedule table
                tables = soup.select('table')
                for table in tables:
                    rows = table.select('tr')
                    for row in rows:
                        cells = row.select('td')
                        if len(cells) >= 2:
                            # Date is typically in the first cell
                            date_text = cells[0].get_text(strip=True)
                            
                            try:
                                # BLS typically formats dates as MM/DD/YYYY
                                if '/' in date_text:
                                    parts = date_text.split('/')
                                    if len(parts) == 3:
                                        month = int(parts[0])
                                        day = int(parts[1])
                                        year_val = int(parts[2])
                                        cpi_dates.append((year_val, month, day))
                            except (ValueError, IndexError):
                                pass
                
                # If we successfully found dates, update cache and return
                if cpi_dates:
                    _cpi_cache = cpi_dates
                    _cpi_cache_expiry = cache_expiry
                    # Filter by year if specified
                    if year is not None:
                        return [date_tuple for date_tuple in cpi_dates if date_tuple[0] == year]
                    return cpi_dates
        
        except Exception as e:
            print(f"Error fetching CPI dates from BLS website: {e}")
        
        # If web scraping fails, estimate based on typical release pattern
        # CPI is typically released around the 10th-15th of each month for the previous month
        today = datetime.date.today()
        estimated_dates = []
        
        # Generate estimates for current year and next year
        for y in range(year, year + 2):
            for month in range(1, 13):
                # Estimate the release day (typically around the 13th of each month)
                # This is a rough estimate and will not be exact
                release_day = 13
                
                # Add to our estimated dates
                estimated_dates.append((y, month, release_day))
        
        _cpi_cache = estimated_dates
        _cpi_cache_expiry = cache_expiry
        # Filter by year if specified
        if year is not None:
            return [date_tuple for date_tuple in estimated_dates if date_tuple[0] == year]
        return estimated_dates
    
    except Exception as e:
        print(f"Error in CPI date estimation: {e}")
        # Return a simple fallback
        today = datetime.date.today()
        return [(year, m, 13) for m in range(1, 13)]

def fetch_earnings_season_periods():
    """
    Determine when earnings seasons are occurring.
    
    Typical earnings seasons:
    - Q1: Early-mid April through early May
    - Q2: Mid July through early August
    - Q3: Mid October through early November
    - Q4: Late January through mid February
    
    Returns:
        List of tuples (start_date, end_date) for current and upcoming earnings seasons
    """
    global _earnings_cache, _earnings_cache_expiry
    
    # Check if we have a valid cache
    current_time = datetime.datetime.now()
    if _earnings_cache and _earnings_cache_expiry and _earnings_cache_expiry > current_time:
        return _earnings_cache
    
    try:
        # Set cache expiry for 24 hours
        cache_expiry = current_time + datetime.timedelta(hours=24)
        
        # Today's date
        today = datetime.date.today()
        
        # Get the current year
        current_year = today.year
        
        # Define the typical earnings season periods
        earnings_seasons = [
            # Q4 earnings (reported in Jan-Feb)
            (datetime.date(current_year, 1, 25), datetime.date(current_year, 2, 15)),
            # Q1 earnings (reported in Apr-May)
            (datetime.date(current_year, 4, 10), datetime.date(current_year, 5, 5)),
            # Q2 earnings (reported in Jul-Aug)
            (datetime.date(current_year, 7, 15), datetime.date(current_year, 8, 10)),
            # Q3 earnings (reported in Oct-Nov)
            (datetime.date(current_year, 10, 15), datetime.date(current_year, 11, 10)),
            # Next year's Q4 earnings
            (datetime.date(current_year + 1, 1, 25), datetime.date(current_year + 1, 2, 15))
        ]
        
        # Try to enhance with actual data from financial APIs or websites
        # This would be implemented in a production environment
        
        _earnings_cache = earnings_seasons
        _earnings_cache_expiry = cache_expiry
        return earnings_seasons
    
    except Exception as e:
        print(f"Error in earnings season estimation: {e}")
        # Return a simple fallback
        today = datetime.date.today()
        return [(today, today + datetime.timedelta(days=30))]

def is_in_earnings_season(event_date: datetime.datetime) -> bool:
    """
    Check if a given date falls within an earnings season.
    
    Args:
        event_date: Date to check
        
    Returns:
        Boolean indicating whether the date is in an earnings season
    """
    event_date_only = event_date.date()
    
    # Get earnings seasons
    earnings_seasons = fetch_earnings_season_periods()
    
    # Check if date falls within any earnings season period
    for start_date, end_date in earnings_seasons:
        if start_date <= event_date_only <= end_date:
            return True
            
    return False

def get_next_cpi_release(event_date: datetime.datetime) -> Tuple[datetime.date, int]:
    """
    Get the next CPI release date and days until that release.
    
    Args:
        event_date: The date to calculate from
        
    Returns:
        Tuple containing (next_release_date, days_until_release)
    """
    # Convert to date if datetime
    base_date = event_date.date() if isinstance(event_date, datetime.datetime) else event_date
    
    # Get current year and next year CPI releases
    current_year = base_date.year
    next_year = current_year + 1
    
    # Fetch CPI release dates for current and next year
    current_year_releases = fetch_cpi_release_dates(current_year)
    next_year_releases = fetch_cpi_release_dates(next_year)
    
    # Combine all releases
    all_releases = current_year_releases + next_year_releases
    
    # Convert tuples to dates
    release_dates = [datetime.date(year, month, day) for year, month, day in all_releases]
    
    # Find the next release date
    future_releases = [d for d in release_dates if d >= base_date]
    
    if not future_releases:
        # If no future releases found, estimate
        estimated_date = base_date.replace(day=13) + datetime.timedelta(days=32)
        estimated_date = estimated_date.replace(day=13)
        return estimated_date, (estimated_date - base_date).days
    
    next_release = min(future_releases)
    days_until = (next_release - base_date).days
    
    return next_release, days_until

def is_cpi_week(event_date: datetime.datetime) -> bool:
    """
    Check if a given date falls within a CPI release week.
    
    Args:
        event_date: Date to check
        
    Returns:
        Boolean indicating whether the date is in a CPI release week
    """
    # Get next CPI release
    next_cpi = get_next_cpi_release(event_date)
    
    if next_cpi:
        release_date, days_until = next_cpi
        # Consider it CPI week if the release is within 3 days before or after
        return abs(days_until) <= 3
        
    return False

def get_next_fomc_meeting(event_date: datetime.datetime) -> Optional[Tuple[datetime.date, int, bool]]:
    """
    Calculate the date of the next FOMC meeting and days until it occurs.
    
    Args:
        event_date: Current date to calculate from
        
    Returns:
        Tuple containing (next meeting date, days until meeting, is important meeting) or None if not found
    """
    event_date_only = event_date.date()
    
    # Fetch FOMC meeting dates (tries to use dynamic data with fallback to hardcoded)
    fomc_schedule = fetch_fomc_meeting_dates()
    
    # Convert schedule to datetime.date objects
    fomc_dates = [(datetime.date(year, month, day), is_important) for year, month, day, is_important in fomc_schedule]
    
    # Find the next meeting
    future_meetings = [(meeting_date, (meeting_date - event_date_only).days, is_important) 
                      for meeting_date, is_important in fomc_dates 
                      if meeting_date >= event_date_only]
    
    if future_meetings:
        # Return the closest future meeting
        return future_meetings[0]
    
    # If no future meetings in our schedule, return the most recent past meeting
    past_meetings = [(meeting_date, (meeting_date - event_date_only).days, is_important) 
                    for meeting_date, is_important in fomc_dates 
                    if meeting_date < event_date_only]
    
    if past_meetings:
        # Return the most recent past meeting
        return sorted(past_meetings, key=lambda x: x[1], reverse=True)[0]
    
    return None

def is_fed_week(event_date: datetime.datetime) -> bool:
    """
    Check if a given date falls within a Fed meeting week.
    
    Args:
        event_date: Date to check
        
    Returns:
        Boolean indicating whether the date is in a Fed meeting week
    """
    # Get next FOMC meeting
    next_fomc = get_next_fomc_meeting(event_date)
    
    if next_fomc:
        meeting_date, days_until, _ = next_fomc
        # Consider it Fed week if the meeting is within 3 days before or after
        return abs(days_until) <= 3
        
    return False

def build_prompt_context(
    event_date: datetime.datetime,
    macro_snapshot: Dict[str, float],
    event_tags: Dict[str, bool]
) -> Dict[str, str]:
    """
    Build enhanced contextual information for LLM prompts based on macroeconomic data and event tags.
    
    This function analyzes the provided economic data and event context to generate
    three types of enhanced contextual information:
    
    1. Time-aware text: Describes current market conditions in a time-aware way, including calendar context
    2. Delta description: Highlights significant recent changes in key indicators vs. expectations
    3. Relevance weights: Identifies which indicators are most important for this event with interpretations
    
    Args:
        event_date: Date and time when the event occurred
        macro_snapshot: Dictionary of macroeconomic indicators and their values
        event_tags: Dictionary of boolean tags providing event context
        
    Returns:
        Dictionary containing three strings:
        - time_aware_text: Description of current market conditions with calendar awareness
        - delta_description: Description of significant recent changes vs. expectations
        - relevance_weights: Description of indicator importance with interpretations
    """
    # Initialize default empty result
    result = {
        "time_aware_text": "",
        "delta_description": "",
        "relevance_weights": ""
    }
    
    # Check if required data is available
    if not macro_snapshot:
        return result
    
    # 1. Generate time-aware text about market conditions with calendar context
    time_aware_text = generate_time_aware_text(event_date, macro_snapshot, event_tags)
    
    # 2. Identify and describe significant deltas vs. expected values
    delta_description = generate_delta_description(macro_snapshot)
    
    # 3. Determine which indicators are most relevant with interpretations
    relevance_weights = generate_relevance_weights(macro_snapshot, event_tags)
    
    # Return the enhanced context
    return {
        "time_aware_text": time_aware_text,
        "delta_description": delta_description,
        "relevance_weights": relevance_weights
    }

def generate_time_aware_text(
    event_date: datetime.datetime,
    macro_snapshot: Dict[str, float],
    event_tags: Dict[str, bool]
) -> str:
    """
    Generate a description of current market conditions in a time-aware way,
    including calendar context like days until next FOMC meeting.
    
    Args:
        event_date: Date and time when the event occurred
        macro_snapshot: Dictionary of macroeconomic indicators and their values
        event_tags: Dictionary of boolean tags providing event context
        
    Returns:
        String describing current market conditions with calendar awareness
    """
    # Format the current date in a human-readable format
    date_str = event_date.strftime('%B %d, %Y')
    
    # Extract key indicators (if available)
    cpi = macro_snapshot.get("CPI_YoY")
    fed_rate = macro_snapshot.get("FedFundsRate")
    unemployment = macro_snapshot.get("Unemployment")
    vix = macro_snapshot.get("VIX")
    treasury10y = macro_snapshot.get("Treasury10Y")
    treasury2y = macro_snapshot.get("Treasury2Y")
    
    # Determine market environment characterizations
    inflation_env = "high-inflation" if cpi and cpi > 4.0 else "moderate-inflation" if cpi and cpi > 2.5 else "low-inflation"
    
    rate_env = "high-rate" if fed_rate and fed_rate > 4.0 else "moderate-rate" if fed_rate and fed_rate > 2.0 else "low-rate"
    
    vol_env = "high-volatility" if vix and vix > 25 else "moderate-volatility" if vix and vix > 15 else "low-volatility"
    
    # Check for yield curve inversion (2-year yield > 10-year yield)
    inverted_yield = treasury2y and treasury10y and treasury2y > treasury10y
    yield_curve = "inverted yield curve" if inverted_yield else "normal yield curve"
    
    # Calculate days until next FOMC meeting using dynamic data
    fomc_info = get_next_fomc_meeting(event_date)
    fomc_context = ""
    if fomc_info:
        next_meeting_date, days_until, is_important = fomc_info
        meeting_type = "important FOMC meeting with press conference" if is_important else "FOMC meeting"
        
        if days_until == 0:
            fomc_context = f"Today is an {meeting_type}."
        elif days_until < 0:
            fomc_context = f"The last {meeting_type} was {abs(days_until)} days ago."
        else:
            fomc_context = f"The next {meeting_type} is in {days_until} days."
    
    # Get CPI release information using dynamic data
    cpi_info = get_next_cpi_release(event_date)
    cpi_context = ""
    if cpi_info:
        release_date, days_until = cpi_info
        if days_until == 0:
            cpi_context = " CPI data is being released today."
        elif days_until < 0:
            cpi_context = f" CPI data was released {abs(days_until)} days ago."
        elif days_until <= 7:
            cpi_context = f" CPI data will be released in {days_until} days."
    
    # Check for earnings season using dynamic data
    earnings_context = ""
    if is_in_earnings_season(event_date):
        earnings_context = " Currently in earnings season."
    
    # Generate market characterization with calendar context
    market_characterization = f"Today is {date_str}. {fomc_context}{cpi_context}{earnings_context} Current market conditions show a {inflation_env}, {rate_env}, {vol_env} environment with an {yield_curve}."
    
    # Dynamically check special periods or use event tags if already provided
    special_periods = []
    
    # Use event tags if provided, otherwise use our dynamic helpers
    if "is_fed_week" in event_tags:
        if event_tags.get("is_fed_week"):
            special_periods.append("Fed meeting week")
    elif is_fed_week(event_date):
        special_periods.append("Fed meeting week")
        
    if "is_cpi_week" in event_tags:
        if event_tags.get("is_cpi_week"):
            special_periods.append("CPI release week")
    elif is_cpi_week(event_date):
        special_periods.append("CPI release week")
        
    if "is_earnings_season" in event_tags:
        if event_tags.get("is_earnings_season"):
            special_periods.append("earnings season")
    elif is_in_earnings_season(event_date):
        special_periods.append("earnings season")
        
    if special_periods:
        market_characterization += f" This is occurring during {' and '.join(special_periods)}."
    
    # Add surprise context if available
    if event_tags.get("surprise_positive") is not None:
        surprise_type = "positive" if event_tags.get("surprise_positive") else "negative"
        market_characterization += f" The market has recently experienced a {surprise_type} surprise."
    
    # Add repeat event context if available
    if event_tags.get("is_repeat_event"):
        market_characterization += " This is a repeat of a recent market event."
        
    return market_characterization

def generate_delta_description(macro_snapshot: Dict[str, float]) -> str:
    """
    Generate a description of significant recent changes in economic indicators,
    with emphasis on comparing actual values vs. expected values.
    
    Args:
        macro_snapshot: Dictionary of macroeconomic indicators and their values
        
    Returns:
        String describing significant deltas from expectations and recent changes
    """
    # First, check for direct expectation vs. actual comparisons
    surprise_comparisons = []
    
    # Common expected vs. actual patterns to check
    expectation_patterns = [
        ("CPI_YoY", "CPI_Expected"),
        ("CoreCPI", "CoreCPI_Expected"),
        ("GDP_QoQ", "GDP_Expected"),
        ("Unemployment", "Unemployment_Expected"),
        ("NFP", "NFP_Expected"),
        ("RetailSales", "RetailSales_Expected")
    ]
    
    # Check for each comparison pair
    for actual_key, expected_key in expectation_patterns:
        if actual_key in macro_snapshot and expected_key in macro_snapshot:
            actual = macro_snapshot[actual_key]
            expected = macro_snapshot[expected_key]
            
            if actual is not None and expected is not None:
                delta = actual - expected
                abs_delta = abs(delta)
                
                # Determine if this is a significant surprise
                threshold = SIGNIFICANT_DELTA_THRESHOLD.get(actual_key, SIGNIFICANT_DELTA_THRESHOLD["DEFAULT"])
                
                if abs_delta > threshold:
                    direction = "above" if delta > 0 else "below"
                    
                    # Format based on indicator type
                    if "CPI" in actual_key or "GDP" in actual_key or "RetailSales" in actual_key:
                        surprise_text = f"{actual_key} surprise: {actual:.1f}% vs. {expected:.1f}% expected ({delta:+.1f}% {direction})"
                    elif "Unemployment" in actual_key:
                        surprise_text = f"{actual_key} surprise: {actual:.1f}% vs. {expected:.1f}% expected ({delta:+.1f}% {direction})"
                    elif "NFP" in actual_key:
                        surprise_text = f"{actual_key} surprise: {int(actual):,} vs. {int(expected):,} expected ({int(delta):+,} {direction})"
                    else:
                        surprise_text = f"{actual_key} surprise: {actual:.2f} vs. {expected:.2f} expected ({delta:+.2f} {direction})"
                        
                    surprise_comparisons.append(surprise_text)
    
    # Next, check for change/delta fields
    significant_changes = []
    
    # Look for change indicators in different formats
    for indicator, value in macro_snapshot.items():
        # Skip metadata fields
        if indicator.startswith("_"):
            continue
            
        # Check if this is a change/delta field
        is_change_field = any(suffix in indicator for suffix in ["_change", "_delta", "_Change", "_Delta"])
        base_indicator = indicator.split("_change")[0].split("_delta")[0].split("_Change")[0].split("_Delta")[0]
        
        if is_change_field and value is not None:
            # Determine if this change is significant using thresholds
            threshold = SIGNIFICANT_DELTA_THRESHOLD.get(base_indicator, SIGNIFICANT_DELTA_THRESHOLD["DEFAULT"])
            
            # For percentage changes, compare to the threshold directly
            # For absolute changes, we need the base value to determine significance
            if abs(value) > threshold:
                # Format the change description
                direction = "increased" if value > 0 else "decreased"
                
                # Special formatting for specific indicators
                if "CPI" in indicator or "GDP" in indicator or "FedFundsRate" in indicator or "Treasury" in indicator:
                    change_text = f"{base_indicator} has {direction} by {abs(value):.1f} percentage points"
                elif "VIX" in indicator:
                    change_text = f"{base_indicator} has {direction} by {abs(value):.1f} points"
                else:
                    change_text = f"{base_indicator} has {direction} by {abs(value):.2f}"
                    
                significant_changes.append(change_text)
    
    # If no explicit change fields found, look for a metadata field with dates to calculate staleness
    macro_date = None
    for key in macro_snapshot:
        if key in ["_timestamp", "_date", "_last_updated"]:
            try:
                macro_date = datetime.datetime.fromisoformat(macro_snapshot[key])
                break
            except (ValueError, TypeError):
                pass
    
    # Combine surprise comparisons and significant changes
    all_changes = []
    
    if surprise_comparisons:
        all_changes.append("Economic data surprises: " + "; ".join(surprise_comparisons))
    
    if significant_changes:
        all_changes.append("Recent significant changes: " + "; ".join(significant_changes))
    
    # Build the final description
    if all_changes:
        return " ".join(all_changes) + "."
    elif macro_date:
        # If no changes but we have a date, indicate data age
        days_old = (datetime.datetime.now() - macro_date).days
        if days_old <= 1:
            return "Using the latest economic data (updated today)."
        elif days_old <= 7:
            return f"Using recent economic data (updated {days_old} days ago)."
        else:
            return f"Using somewhat dated economic data (updated {days_old} days ago)."
    else:
        # No deltas, no date - generic message
        return "Recent economic indicators show no significant changes from expectations."

def generate_relevance_weights(
    macro_snapshot: Dict[str, float],
    event_tags: Dict[str, bool]
) -> str:
    """
    Generate a description of which indicators are most relevant for this event,
    including interpretations of their current values.
    
    Args:
        macro_snapshot: Dictionary of macroeconomic indicators and their values
        event_tags: Dictionary of boolean tags providing event context
        
    Returns:
        String describing indicator importance with interpretations
    """
    # Determine event type from tags or use default weights
    event_type = None
    
    # Check event tags to infer event type
    if event_tags.get("is_fed_week"):
        event_type = "Monetary Policy"
    elif event_tags.get("is_cpi_week"):
        event_type = "Inflation"
    elif event_tags.get("is_earnings_season"):
        event_type = "Earnings"
    
    # Get weights for this event type or use balanced weights
    if event_type and event_type in EVENT_TYPE_WEIGHTS:
        weights = EVENT_TYPE_WEIGHTS[event_type]
    else:
        # Use a balanced approach if no specific event type
        weights = {
            "CPI_YoY": 7,
            "FedFundsRate": 7,
            "VIX": 7,
            "Treasury10Y": 6,
            "GDP_QoQ": 6,
            "Unemployment": 6
        }
    
    # Filter to include only indicators that are actually in our snapshot
    available_indicators = [ind for ind in weights if ind in macro_snapshot]
    
    # Sort by importance (weight)
    sorted_indicators = sorted(
        available_indicators, 
        key=lambda x: weights.get(x, 0), 
        reverse=True
    )
    
    # Add yield curve signal specifically
    yield_curve_signal = ""
    if "Treasury2Y" in macro_snapshot and "Treasury10Y" in macro_snapshot:
        spread = macro_snapshot["Treasury10Y"] - macro_snapshot["Treasury2Y"]
        if spread < 0:
            yield_curve_signal = "2Y-10Y curve: inverted → high recession risk signal"
        elif spread < 0.1:
            yield_curve_signal = "2Y-10Y curve: flat → caution signal"
        elif spread < 0.5:
            yield_curve_signal = "2Y-10Y curve: normal → neutral signal"
        else:
            yield_curve_signal = "2Y-10Y curve: steep → growth signal"
    
    # Format into description with interpretations
    indicator_interpretations = []
    
    # Add yield curve signal first if available
    if yield_curve_signal:
        indicator_interpretations.append(yield_curve_signal)
    
    # Add interpretations for top indicators
    if sorted_indicators:
        # Take top indicators depending on how many we have
        top_n = min(len(sorted_indicators), 4)  # Limit to 4 since we might add the yield curve
        top_indicators = sorted_indicators[:top_n]
        
        for indicator in top_indicators:
            if indicator in macro_snapshot and indicator in INDICATOR_INTERPRETATIONS:
                value = macro_snapshot[indicator]
                
                # Find the appropriate interpretation threshold
                interpretation = ""
                signal = ""
                for threshold, interp, sig in INDICATOR_INTERPRETATIONS[indicator]:
                    if value >= threshold:
                        interpretation = interp
                        signal = sig
                        break
                
                if interpretation and signal:
                    # Add importance weight too
                    weight_term = "high" if weights.get(indicator, 0) >= 8 else "medium" if weights.get(indicator, 0) >= 5 else "low"
                    interp_text = f"{indicator}: {value:.1f}% ({interpretation}) → {weight_term} {signal}"
                    indicator_interpretations.append(interp_text)
    
    if indicator_interpretations:
        return "Key indicators and signals: " + "; ".join(indicator_interpretations) + "."
    else:
        return "No specific indicators identified as providing strong signals currently."

def get_current_market_phase(
    macro_snapshot: Dict[str, float]
) -> str:
    """
    Determine the current market phase based on macroeconomic indicators.
    
    Args:
        macro_snapshot: Dictionary of macroeconomic indicators and their values
        
    Returns:
        String describing the current market phase
    """
    # Extract key indicators (if available)
    cpi = macro_snapshot.get("CPI_YoY")
    fed_rate = macro_snapshot.get("FedFundsRate")
    unemployment = macro_snapshot.get("Unemployment")
    gdp = macro_snapshot.get("GDP_QoQ")
    
    # Check for yield curve inversion (2-year yield > 10-year yield)
    treasury2y = macro_snapshot.get("Treasury2Y")
    treasury10y = macro_snapshot.get("Treasury10Y")
    inverted_yield = treasury2y and treasury10y and treasury2y > treasury10y
    
    # Determine market phase
    if inverted_yield and fed_rate and fed_rate > 4.0:
        if unemployment and unemployment > 5.0:
            return "late-cycle recession"
        else:
            return "late-cycle pre-recession"
    elif fed_rate and fed_rate > 3.0 and cpi and cpi > 3.0:
        return "late-cycle inflation fighting"
    elif fed_rate and fed_rate < 2.0 and cpi and cpi < 2.0:
        if gdp and gdp > 2.0:
            return "early-cycle expansion"
        else:
            return "early-cycle recovery"
    elif fed_rate and fed_rate < 1.0:
        return "accommodative stimulus phase"
    else:
        return "mid-cycle normal growth"

# Demo usage if run directly
if __name__ == "__main__":
    # Example data
    example_date = datetime.datetime.now()
    example_macro = {
        "CPI_YoY": 3.2,
        "CPI_Expected": 3.4,  # Expected CPI
        "CoreCPI": 2.8,
        "FedFundsRate": 5.25,
        "Unemployment": 3.8,
        "Unemployment_Expected": 4.0,  # Expected unemployment
        "VIX": 18.5,
        "Treasury10Y": 4.1,
        "Treasury2Y": 4.8,
        "GDP_QoQ": 2.1,
        "GDP_Expected": 1.8,  # Expected GDP
        "CPI_YoY_change": -0.5,
        "VIX_change": 3.2,
        "_timestamp": datetime.datetime.now().isoformat()
    }
    example_tags = {
        "surprise_positive": True,
        "is_fed_week": True,
        "is_cpi_week": False,
        "is_earnings_season": False,
        "is_repeat_event": False
    }
    
    # Generate enhanced context
    context = build_prompt_context(
        event_date=example_date,
        macro_snapshot=example_macro,
        event_tags=example_tags
    )
    
    # Print the results
    print("=== PROMPT CONTEXT BUILDER EXAMPLE ===")
    print("\nTime-Aware Text:")
    print(context["time_aware_text"])
    print("\nDelta Description:")
    print(context["delta_description"])
    print("\nRelevance Weights:")
    print(context["relevance_weights"])
    
    print("\nCurrent Market Phase:")
    print(get_current_market_phase(example_macro)) 