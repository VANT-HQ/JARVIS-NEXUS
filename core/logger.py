# core/logger.py  
"""
JARVIS Central Logging System
============================

Provides centralized logging configuration for the JARVIS engine.
Features automatic log rotation/cleanup by retention hours (default 24h)
and custom structured formatting for clean production monitoring.
"""

import logging
import logging.handlers
import re
from datetime import datetime, timedelta
from pathlib import Path
from core.config import LOGS_DIR


def setup_logger(log_name: str = "jarvis_nexus.log") -> logging.Logger:
    """
    Initializes and configures the central logging system.
    Filters warnings, errors, and critical log lines, handles rotation constraints, and returns a root logger.
    """
    logger = logging.getLogger()
    
    if logger.hasHandlers():
        return logger

    logger.setLevel(logging.ERROR)
    log_file = LOGS_DIR / log_name

    # Clean up logs older than 24 hours before opening the file handler
    _cleanup_old_logs(log_file, hours=24)

    file_handler = logging.FileHandler(
        filename=log_file,
        mode='a',
        encoding='utf-8'
    )
    
    formatter = logging.Formatter(
        "[{asctime}] | {levelname:^8} | [{module:^15}] : {message}",
        datefmt="%Y-%m-%d %H:%M:%S",
        style='{'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Suppress external verbose API calls to keep logs clean
    logging.getLogger("httpx").setLevel(logging.CRITICAL)
    logging.getLogger("urllib3").setLevel(logging.CRITICAL)
    
    logging.info("==================================================")
    logging.info("         JARVIS NEXUS LOGGER INITIALIZED         ")
    logging.info("==================================================")
    
    return logger


def _cleanup_old_logs(log_file: Path, hours: int = 24) -> None:
    """
    Parses the log file and retains lines written within the retention window.
    Removes lines exceeding the specified hour threshold based on their timestamp.
    """
    if not log_file.exists():
        return
        
    try:
        now = datetime.now()
        cutoff_time = now - timedelta(hours=hours)
        
        timestamp_pattern = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]")
        
        lines_to_keep = []
        last_valid = True 
        
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        for line in lines:
            match = timestamp_pattern.match(line)
            if match:
                time_str = match.group(1)
                try:
                    log_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                    if log_time >= cutoff_time:
                        lines_to_keep.append(line)
                        last_valid = True
                    else:
                        last_valid = False
                except ValueError:
                    lines_to_keep.append(line)
                    last_valid = True
            else:
                if last_valid:
                    lines_to_keep.append(line)
                    
        with open(log_file, 'w', encoding='utf-8') as f:
            f.writelines(lines_to_keep)
            
    except Exception as e:
        print(f"Warning: Failed to clean old logs: {e}")