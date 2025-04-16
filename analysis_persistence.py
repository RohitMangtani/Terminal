"""
Analysis Persistence Module

This module handles saving, retrieving, and managing historical analysis results
for future reference and reuse. It provides functions to persist analysis results
to disk and retrieve them when needed.

Enhanced with cloud storage capabilities and improved scalability.
"""

import os
import json
import datetime
import re
import requests
from typing import Dict, List, Optional, Union, Any
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
DEFAULT_ANALYSIS_DIR = "analysis_history"
DEFAULT_EVENTS_FILE = "historical_events.json"
DEFAULT_SIMILAR_EVENTS_FILE = "similar_events.json"
DEFAULT_INDEX_FILE = "analysis_index.json"
MAX_RESULTS_PER_FILE = 100  # Max number of analyses to store in a single file

# Flag to enable cloud storage (when implemented)
USE_CLOUD_STORAGE = False
CLOUD_STORAGE_API_ENDPOINT = "https://api.storage.example.com"
CLOUD_STORAGE_API_KEY = os.environ.get("CLOUD_STORAGE_API_KEY", "")

class AnalysisPersistence:
    """Class to handle saving and retrieving historical analysis results"""
    
    def __init__(self, 
                 base_dir: str = DEFAULT_ANALYSIS_DIR, 
                 events_file: str = DEFAULT_EVENTS_FILE,
                 similar_events_file: str = DEFAULT_SIMILAR_EVENTS_FILE,
                 index_file: str = DEFAULT_INDEX_FILE,
                 use_cloud: bool = USE_CLOUD_STORAGE):
        """
        Initialize the persistence manager
        
        Args:
            base_dir: Directory to store analysis files
            events_file: File to store historical event analyses
            similar_events_file: File to store similar events analyses
            index_file: File to store the index of all analyses
            use_cloud: Whether to use cloud storage when available
        """
        self.base_dir = base_dir
        self.events_file = events_file
        self.similar_events_file = similar_events_file
        self.index_file = index_file
        self.use_cloud = use_cloud
        
        # Create directories if they don't exist
        self._ensure_directories()
        
        # Load existing indices
        self.event_index = self._load_index()
    
    def _ensure_directories(self) -> None:
        """Create necessary directories if they don't exist"""
        if not os.path.exists(self.base_dir):
            os.makedirs(self.base_dir)
            logger.info(f"Created analysis directory: {self.base_dir}")
        
        # Create subdirectories for different types of analyses
        for subdir in ['events', 'similar_events', 'queries']:
            subdir_path = os.path.join(self.base_dir, subdir)
            if not os.path.exists(subdir_path):
                os.makedirs(subdir_path)
                logger.info(f"Created subdirectory: {subdir_path}")
    
    def _load_index(self) -> Dict:
        """Load the index of all analyses from disk or cloud"""
        # Try to load from cloud first if enabled
        if self.use_cloud:
            try:
                cloud_index = self._get_from_cloud(self.index_file)
                if cloud_index:
                    logger.info("Loaded analysis index from cloud storage")
                    return cloud_index
            except Exception as e:
                logger.error(f"Error loading index from cloud: {str(e)}")
        
        # Fallback to local storage
        index_path = os.path.join(self.base_dir, self.index_file)
        if os.path.exists(index_path):
            try:
                with open(index_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading analysis index: {str(e)}")
                return {"events": {}, "similar_events": {}, "last_updated": "", "query_history": []}
        else:
            # Create default index structure
            return {"events": {}, "similar_events": {}, "last_updated": "", "query_history": []}
    
    def _save_index(self) -> None:
        """Save the index of all analyses to disk and cloud if enabled"""
        self.event_index["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Save to disk
        index_path = os.path.join(self.base_dir, self.index_file)
        try:
            with open(index_path, 'w') as f:
                json.dump(self.event_index, f, indent=2)
            logger.info(f"Saved analysis index to {index_path}")
            
            # Also save to cloud if enabled
            if self.use_cloud:
                self._save_to_cloud(self.index_file, self.event_index)
                logger.info("Saved analysis index to cloud storage")
        except Exception as e:
            logger.error(f"Error saving analysis index: {str(e)}")
    
    def _get_storage_path(self, analysis_type: str, key: str) -> str:
        """
        Get the path where an analysis should be stored
        
        Args:
            analysis_type: Type of analysis ('events', 'similar_events', 'queries')
            key: Unique identifier for the analysis
            
        Returns:
            str: Path to the file where the analysis should be stored
        """
        # Create a safe filename from the key
        safe_key = "".join(c if c.isalnum() else "_" for c in key)
        safe_key = safe_key[:50]  # Limit length
        
        # Create timestamp part for uniqueness
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Generate filename
        filename = f"{safe_key}_{timestamp}.json"
        
        return os.path.join(self.base_dir, analysis_type, filename)
    
    def _save_to_cloud(self, filename: str, data: Dict) -> bool:
        """
        Save data to cloud storage
        
        Args:
            filename: Name of file to save
            data: Data to save
            
        Returns:
            bool: True if successful, False if failed
        """
        # This is a placeholder for a real cloud storage integration
        # Example with a cloud storage API like AWS S3, Google Cloud Storage or free alternatives
        try:
            # Example API call to a cloud storage service
            # headers = {"Authorization": f"Bearer {CLOUD_STORAGE_API_KEY}"}
            # response = requests.post(
            #     f"{CLOUD_STORAGE_API_ENDPOINT}/upload",
            #     headers=headers,
            #     json={"filename": filename, "data": data}
            # )
            # return response.status_code == 200
            logger.info(f"[SIMULATION] Saved {filename} to cloud storage")
            return True
        except Exception as e:
            logger.error(f"Error saving to cloud storage: {str(e)}")
            return False
    
    def _get_from_cloud(self, filename: str) -> Optional[Dict]:
        """
        Get data from cloud storage
        
        Args:
            filename: Name of file to get
            
        Returns:
            Dict: Data from cloud storage or None if not found/error
        """
        # This is a placeholder for a real cloud storage integration
        try:
            # Example API call to a cloud storage service
            # headers = {"Authorization": f"Bearer {CLOUD_STORAGE_API_KEY}"}
            # response = requests.get(
            #     f"{CLOUD_STORAGE_API_ENDPOINT}/download/{filename}",
            #     headers=headers
            # )
            # if response.status_code == 200:
            #     return response.json().get("data")
            # return None
            logger.info(f"[SIMULATION] Attempted to get {filename} from cloud storage")
            return None
        except Exception as e:
            logger.error(f"Error getting from cloud storage: {str(e)}")
            return None
    
    def save_historical_event_analysis(self, event_analysis: Dict, query: str = None) -> str:
        """
        Save a historical event analysis to disk and cloud if enabled
        
        Args:
            event_analysis: Dictionary containing historical event analysis
            query: Optional query that led to this analysis
            
        Returns:
            str: Path to the saved analysis file or empty string if failed
        """
        if not event_analysis.get("success", False):
            logger.warning("Cannot save unsuccessful event analysis")
            return ""
        
        try:
            # Extract key information
            ticker = event_analysis.get("ticker", "unknown")
            event_date = event_analysis.get("event_date", "unknown")
            
            # Generate a unique key for this analysis
            key = f"{ticker}_{event_date}"
            
            # Get storage path
            file_path = self._get_storage_path("events", key)
            
            # Add metadata
            analysis_to_save = event_analysis.copy()
            analysis_to_save["_metadata"] = {
                "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "query": query,
                "file_path": file_path
            }
            
            # Save to disk
            with open(file_path, 'w') as f:
                json.dump(analysis_to_save, f, indent=2)
            
            # Save to cloud if enabled
            if self.use_cloud:
                self._save_to_cloud(os.path.basename(file_path), analysis_to_save)
            
            # Update index
            if ticker not in self.event_index["events"]:
                self.event_index["events"][ticker] = []
            
            # Add to index
            self.event_index["events"][ticker].append({
                "event_date": event_date,
                "price_change": event_analysis.get("price_change_pct", 0),
                "trend": event_analysis.get("trend", "Unknown"),
                "file_path": file_path,
                "saved_at": analysis_to_save["_metadata"]["saved_at"]
            })
            
            # Add to query history if query was provided
            if query:
                query_entry = {
                    "query": query,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "result_type": "historical_event",
                    "ticker": ticker,
                    "event_date": event_date,
                    "file_path": file_path
                }
                self.event_index["query_history"].append(query_entry)
            
            # Save updated index
            self._save_index()
            
            logger.info(f"Saved historical event analysis for {ticker} on {event_date} to {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"Error saving historical event analysis: {str(e)}")
            return ""
    
    def save_similar_events_analysis(self, similar_events_analysis: Dict, query: str = None) -> str:
        """
        Save a similar events analysis to disk and cloud if enabled
        
        Args:
            similar_events_analysis: Dictionary containing similar events analysis
            query: Optional query that led to this analysis
            
        Returns:
            str: Path to the saved analysis file or empty string if failed
        """
        if not similar_events_analysis.get("success", False):
            logger.warning("Cannot save unsuccessful similar events analysis")
            return ""
        
        try:
            # Generate a key based on pattern and dominant ticker
            pattern = similar_events_analysis.get("pattern_summary", "unknown_pattern")
            ticker = similar_events_analysis.get("dominant_ticker", "unknown")
            
            # Create a key
            key = f"{ticker}_{pattern}"
            
            # Get storage path
            file_path = self._get_storage_path("similar_events", key)
            
            # Add metadata
            analysis_to_save = similar_events_analysis.copy()
            analysis_to_save["_metadata"] = {
                "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "query": query,
                "file_path": file_path
            }
            
            # Save to disk
            with open(file_path, 'w') as f:
                json.dump(analysis_to_save, f, indent=2)
            
            # Save to cloud if enabled
            if self.use_cloud:
                self._save_to_cloud(os.path.basename(file_path), analysis_to_save)
            
            # Update index
            if pattern not in self.event_index["similar_events"]:
                self.event_index["similar_events"][pattern] = []
            
            # Add to index
            self.event_index["similar_events"][pattern].append({
                "dominant_ticker": ticker,
                "avg_price_change": similar_events_analysis.get("avg_price_change", 0),
                "consistency_score": similar_events_analysis.get("consistency_score", 0),
                "file_path": file_path,
                "saved_at": analysis_to_save["_metadata"]["saved_at"]
            })
            
            # Add to query history if query was provided
            if query:
                query_entry = {
                    "query": query,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "result_type": "similar_events",
                    "pattern": pattern,
                    "dominant_ticker": ticker,
                    "file_path": file_path
                }
                self.event_index["query_history"].append(query_entry)
            
            # Save updated index
            self._save_index()
            
            logger.info(f"Saved similar events analysis for {pattern} to {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"Error saving similar events analysis: {str(e)}")
            return ""
    
    def save_query_result(self, query: str, event_analysis: Dict = None, similar_events_analysis: Dict = None) -> Dict:
        """
        Save complete query results including historical event and similar events analyses
        
        Args:
            query: User's query string
            event_analysis: Optional historical event analysis
            similar_events_analysis: Optional similar events analysis
            
        Returns:
            Dict: Paths to saved files
        """
        result = {"query": query, "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        
        # Save historical event analysis if provided
        if event_analysis and event_analysis.get("success", False):
            event_path = self.save_historical_event_analysis(event_analysis, query)
            if event_path:
                result["event_analysis_path"] = event_path
        
        # Save similar events analysis if provided
        if similar_events_analysis and similar_events_analysis.get("success", False):
            similar_path = self.save_similar_events_analysis(similar_events_analysis, query)
            if similar_path:
                result["similar_events_path"] = similar_path
        
        # Get a path for the complete query result
        query_path = self._get_storage_path("queries", query)
        
        # Save the complete result
        try:
            with open(query_path, 'w') as f:
                json.dump(result, f, indent=2)
            
            # Save to cloud if enabled
            if self.use_cloud:
                self._save_to_cloud(os.path.basename(query_path), result)
                
            result["query_path"] = query_path
            logger.info(f"Saved complete query result for '{query}' to {query_path}")
        except Exception as e:
            logger.error(f"Error saving complete query result: {str(e)}")
        
        return result
    
    def find_historical_analysis(self, ticker: str = None, event_date: str = None, 
                                date_range: tuple = None) -> List[Dict]:
        """
        Find historical event analyses matching the criteria
        
        Args:
            ticker: Ticker symbol to search for
            event_date: Specific event date to match
            date_range: Tuple of (start_date, end_date) to search within
            
        Returns:
            List of matching analyses (metadata only, not full content)
        """
        results = []
        
        # Check if we have any saved analyses
        if not self.event_index["events"]:
            return []
        
        # If ticker is provided, search only in that ticker's data
        if ticker:
            tickers_to_search = [ticker] if ticker in self.event_index["events"] else []
        else:
            tickers_to_search = list(self.event_index["events"].keys())
        
        # Search through the specified tickers
        for tick in tickers_to_search:
            for analysis in self.event_index["events"][tick]:
                # Check if the analysis matches our criteria
                if event_date and analysis["event_date"] != event_date:
                    continue
                
                if date_range:
                    start_date, end_date = date_range
                    analysis_date = analysis["event_date"]
                    if analysis_date < start_date or analysis_date > end_date:
                        continue
                
                # Add to results
                results.append(analysis)
        
        return results
    
    def find_similar_events_analysis(self, pattern: str = None, ticker: str = None) -> List[Dict]:
        """
        Find similar events analyses matching the criteria
        
        Args:
            pattern: Pattern summary to search for
            ticker: Dominant ticker to search for
            
        Returns:
            List of matching analyses (metadata only, not full content)
        """
        results = []
        
        # Check if we have any saved analyses
        if not self.event_index["similar_events"]:
            return []
        
        # If pattern is provided, search only in that pattern's data
        if pattern:
            patterns_to_search = [pattern] if pattern in self.event_index["similar_events"] else []
        else:
            patterns_to_search = list(self.event_index["similar_events"].keys())
        
        # Search through the specified patterns
        for pat in patterns_to_search:
            for analysis in self.event_index["similar_events"][pat]:
                # Check if the analysis matches our criteria
                if ticker and analysis["dominant_ticker"] != ticker:
                    continue
                
                # Add to results
                results.append(analysis)
        
        return results
    
    def search_query_history(self, query_term: str = None, limit: int = 10) -> List[Dict]:
        """
        Search query history for matching queries
        
        Args:
            query_term: Term to search for in queries
            limit: Maximum number of results to return
            
        Returns:
            List of matching query entries
        """
        if not query_term:
            # Return most recent queries
            return sorted(self.event_index["query_history"], 
                          key=lambda x: x.get("timestamp", ""), 
                          reverse=True)[:limit]
        
        # Search for matching queries
        results = []
        for entry in self.event_index["query_history"]:
            if query_term.lower() in entry["query"].lower():
                results.append(entry)
                
        # Sort by timestamp (newest first) and limit
        results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return results[:limit]
    
    def load_analysis(self, file_path: str) -> Dict:
        """
        Load a specific analysis from disk or cloud
        
        Args:
            file_path: Path to the analysis file
            
        Returns:
            Dict: Analysis data or empty dict if not found
        """
        # Try to load from cloud first if enabled
        if self.use_cloud and os.path.basename(file_path):
            try:
                cloud_data = self._get_from_cloud(os.path.basename(file_path))
                if cloud_data:
                    logger.info(f"Loaded analysis from cloud: {file_path}")
                    return cloud_data
            except Exception as e:
                logger.error(f"Error loading analysis from cloud: {str(e)}")
        
        # Fall back to local file
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    return json.load(f)
            else:
                logger.warning(f"Analysis file not found: {file_path}")
                return {}
        except Exception as e:
            logger.error(f"Error loading analysis from {file_path}: {str(e)}")
            return {}
    
    def get_statistics(self) -> Dict:
        """
        Get statistics about saved analyses
        
        Returns:
            Dict: Dictionary with statistics
        """
        # Count historical event analyses
        total_historical_events = 0
        for ticker in self.event_index["events"]:
            total_historical_events += len(self.event_index["events"][ticker])
        
        # Count similar events analyses
        total_similar_events = 0
        for pattern in self.event_index["similar_events"]:
            total_similar_events += len(self.event_index["similar_events"][pattern])
        
        # Count queries
        total_queries = len(self.event_index["query_history"])
        
        # Get unique tickers
        tickers_analyzed = list(self.event_index["events"].keys())
        
        # Find most analyzed ticker
        most_analyzed_ticker = None
        most_analyses = 0
        for ticker, analyses in self.event_index["events"].items():
            if len(analyses) > most_analyses:
                most_analyses = len(analyses)
                most_analyzed_ticker = ticker
        
        # Find most common pattern
        most_common_pattern = None
        most_pattern_analyses = 0
        for pattern, analyses in self.event_index["similar_events"].items():
            if len(analyses) > most_pattern_analyses:
                most_pattern_analyses = len(analyses)
                most_common_pattern = pattern
        
        # Get most recent query
        most_recent_query = None
        if self.event_index["query_history"]:
            # Sort by timestamp
            sorted_queries = sorted(self.event_index["query_history"], 
                                   key=lambda x: x.get("timestamp", ""), 
                                   reverse=True)
            if sorted_queries:
                most_recent_query = sorted_queries[0].get("query")
        
        # Compile statistics
        stats = {
            "total_historical_events": total_historical_events,
            "total_similar_events": total_similar_events,
            "total_queries": total_queries,
            "tickers_analyzed": tickers_analyzed,
            "most_analyzed_ticker": most_analyzed_ticker,
            "most_common_pattern": most_common_pattern,
            "most_recent_query": most_recent_query,
            "storage_type": "hybrid (local + cloud)" if self.use_cloud else "local only"
        }
        
        return stats

# Create a singleton instance of the persistence manager
_persistence_manager = None

def get_persistence_manager() -> AnalysisPersistence:
    """
    Get the singleton persistence manager
    
    Returns:
        AnalysisPersistence: The persistence manager
    """
    global _persistence_manager
    if _persistence_manager is None:
        _persistence_manager = AnalysisPersistence()
    return _persistence_manager

# Simplified interface for module-level access

def save_historical_analysis(event_analysis: Dict, query: str = None) -> str:
    """
    Save a historical event analysis
    
    Args:
        event_analysis: The analysis data
        query: Optional query string
        
    Returns:
        str: Path to the saved file
    """
    return get_persistence_manager().save_historical_event_analysis(event_analysis, query)

def save_similar_events_analysis(similar_events_analysis: Dict, query: str = None) -> str:
    """
    Save a similar events analysis
    
    Args:
        similar_events_analysis: The analysis data
        query: Optional query string
        
    Returns:
        str: Path to the saved file
    """
    return get_persistence_manager().save_similar_events_analysis(similar_events_analysis, query)

def save_query_result(query: str, event_analysis: Dict = None, similar_events_analysis: Dict = None) -> Dict:
    """
    Save a query result
    
    Args:
        query: The query string
        event_analysis: Optional event analysis
        similar_events_analysis: Optional similar events analysis
        
    Returns:
        Dict: Paths to saved files
    """
    return get_persistence_manager().save_query_result(query, event_analysis, similar_events_analysis)

def find_historical_analysis(ticker: str = None, event_date: str = None, date_range: tuple = None) -> List[Dict]:
    """
    Find historical analyses matching criteria
    
    Args:
        ticker: Optional ticker filter
        event_date: Optional date filter
        date_range: Optional date range filter
        
    Returns:
        List[Dict]: Matching analyses
    """
    return get_persistence_manager().find_historical_analysis(ticker, event_date, date_range)

def find_similar_events_analysis(pattern: str = None, ticker: str = None) -> List[Dict]:
    """
    Find similar events analyses matching criteria
    
    Args:
        pattern: Optional pattern filter
        ticker: Optional ticker filter
        
    Returns:
        List[Dict]: Matching analyses
    """
    return get_persistence_manager().find_similar_events_analysis(pattern, ticker)

def load_analysis(file_path: str) -> Dict:
    """
    Load an analysis from disk or cloud
    
    Args:
        file_path: Path to the analysis file
        
    Returns:
        Dict: The analysis data
    """
    return get_persistence_manager().load_analysis(file_path)

def get_statistics() -> Dict:
    """
    Get statistics about saved analyses
    
    Returns:
        Dict: Statistics
    """
    return get_persistence_manager().get_statistics()

def enable_cloud_storage(enabled: bool = True) -> None:
    """
    Enable or disable cloud storage
    
    Args:
        enabled: Whether to enable cloud storage
    """
    global _persistence_manager
    if _persistence_manager is not None:
        _persistence_manager.use_cloud = enabled
    else:
        # Create the manager with the specified setting
        _persistence_manager = AnalysisPersistence(use_cloud=enabled)

if __name__ == "__main__":
    # Simple test code
    persistence = AnalysisPersistence()
    
    # Generate some sample analyses
    sample_event_analysis = {
        "success": True,
        "ticker": "BTC-USD",
        "event_date": "2024-01-10",
        "price_change_pct": -9.52,
        "trend": "Bearish",
        "max_drawdown_pct": -15.67,
        "days_analyzed": 7
    }
    
    sample_similar_events = {
        "success": True,
        "pattern_summary": "Strong bearish trend with significant volatility",
        "dominant_ticker": "BTC-USD",
        "avg_price_change": -8.75,
        "consistency_score": 85
    }
    
    # Test saving and loading
    event_path = persistence.save_historical_event_analysis(sample_event_analysis, "What happened when Bitcoin ETF was approved?")
    similar_path = persistence.save_similar_events_analysis(sample_similar_events, "What happened when Bitcoin ETF was approved?")
    
    # Print statistics
    stats = persistence.get_statistics()
    print("\nAnalysis Storage Statistics:")
    print("-" * 40)
    for key, value in stats.items():
        print(f"{key}: {value}")
    
    # Find analyses
    btc_analyses = persistence.find_historical_analysis(ticker="BTC-USD")
    print(f"\nFound {len(btc_analyses)} BTC analyses")
    
    # Load a specific analysis
    if event_path:
        loaded_analysis = persistence.load_analysis(event_path)
        print(f"\nLoaded analysis for {loaded_analysis.get('ticker')} on {loaded_analysis.get('event_date')}")
        print(f"Price change: {loaded_analysis.get('price_change_pct')}%") 