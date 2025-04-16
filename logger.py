#!/usr/bin/env python
"""
LOGGER MODULE
============

This module provides a standardized logging setup for the options pipeline system.
It configures loggers to output both to the console and to a log file.

How to Use:
----------
1. Import the logger in your module:
   from logger import get_logger

2. Create a logger instance for your module:
   logger = get_logger(__name__)

3. Use the logger:
   logger.info("Processing started")
   logger.warning("Potential issue detected")
   logger.error("An error occurred", exc_info=True)  # Includes traceback

Available Log Levels:
-------------------
- DEBUG: Detailed information for debugging
- INFO: Confirmation that things are working as expected
- WARNING: Indication that something unexpected happened, but the program is still working
- ERROR: Due to a more serious problem, the program couldn't perform some function
- CRITICAL: A serious error indicating the program may be unable to continue running

Configuration:
------------
- Logs are saved to: pipeline.log
- Console output shows: INFO and above
- File output saves: DEBUG and above
- Log format includes: timestamp, log level, module name, and message
"""

import logging
import os
import sys
from typing import Optional
from datetime import datetime

# Constants
LOG_FILE = "pipeline.log"
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Track if logging has been configured
_logging_configured = False

def configure_logging(log_file: str = LOG_FILE, console_level: int = logging.INFO, 
                     file_level: int = logging.DEBUG) -> None:
    """
    Configure the logging system to output to both console and file.
    
    Args:
        log_file: Path to the log file
        console_level: Minimum log level for console output
        file_level: Minimum log level for file output
    """
    global _logging_configured
    
    if _logging_configured:
        return
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture all logs
    
    # Create formatters
    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    
    # Configure console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Configure file handler
    try:
        # Create directory for log file if it doesn't exist
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(file_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except Exception as e:
        # Still log to console if file logging fails
        console_handler.setLevel(logging.DEBUG)  # Ensure we capture debug logs too
        root_logger.error(f"Failed to configure file logging: {str(e)}")
    
    _logging_configured = True
    root_logger.info(f"Logging configured: console={logging.getLevelName(console_level)}, "
                    f"file={logging.getLevelName(file_level)} at {log_file}")

def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger for the specified module.
    
    Args:
        name: Module name, typically __name__
        
    Returns:
        Configured logger instance
    """
    # Ensure logging is configured
    if not _logging_configured:
        configure_logging()
    
    # Create and return the logger
    return logging.getLogger(name)

# Convenience loggers for quick access
def log_info(message: str, module: str = "root") -> None:
    """Log an info message"""
    get_logger(module).info(message)

def log_warning(message: str, module: str = "root") -> None:
    """Log a warning message"""
    get_logger(module).warning(message)

def log_error(message: str, exc_info: bool = False, module: str = "root") -> None:
    """Log an error message, optionally with exception info"""
    get_logger(module).error(message, exc_info=exc_info)

def log_start_section(title: str, module: str = "root") -> None:
    """Log a section start with a formatted title"""
    logger = get_logger(module)
    logger.info("=" * 80)
    logger.info(f"STARTING: {title}")
    logger.info("=" * 80)

def log_end_section(title: str, module: str = "root") -> None:
    """Log a section end with a formatted title"""
    logger = get_logger(module)
    logger.info("-" * 80)
    logger.info(f"COMPLETED: {title}")
    logger.info("-" * 80)

# Auto-configure logging when the module is imported
configure_logging()

if __name__ == "__main__":
    # Example usage
    logger = get_logger(__name__)
    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")
    
    # Test section logging
    log_start_section("Test Process")
    log_info("Processing test data")
    log_warning("Test warning")
    log_end_section("Test Process")
    
    print(f"Check the log file at: {os.path.abspath(LOG_FILE)}") 