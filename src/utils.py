"""
Utility functions for logging and common operations.
"""

import logging
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse

from config.settings import settings


def setup_logging():
    """Configure logging for the application"""
    # Ensure log directory exists
    settings.LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    log_file = settings.LOG_DIR / f"fund_retriever_{datetime.now().strftime('%Y%m%d')}.log"
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    )
    simple_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL))
    
    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # File handler with detailed formatting
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(file_handler)
    
    # Console handler with simpler formatting
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, settings.LOG_LEVEL))
    console_handler.setFormatter(simple_formatter)
    root_logger.addHandler(console_handler)
    
    # Log the logging setup
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured - Level: {settings.LOG_LEVEL}, Log file: {log_file}")


def validate_fund_symbol(symbol: str) -> bool:
    """Validate fund symbol format"""
    if not symbol or not isinstance(symbol, str):
        return False
    
    # Remove whitespace and convert to uppercase
    symbol = symbol.strip().upper()
    
    # Check length (most fund symbols are 3-5 characters, some ETFs can be longer)
    if len(symbol) < 1 or len(symbol) > 10:
        return False
    
    # Check character set - letters, numbers, and some common special characters
    if not re.match(r'^[A-Z0-9\-\.]+$', symbol):
        return False
    
    # Additional validation rules
    
    # Cannot start or end with special characters
    if symbol.startswith(('-', '.')) or symbol.endswith(('-', '.')):
        return False
    
    # Cannot be all numbers (not a typical fund symbol pattern)
    if symbol.isdigit():
        return False
    
    # Check for common invalid patterns
    invalid_patterns = [
        r'^\-+$',  # All dashes
        r'^\.+$',  # All dots
        r'.*\-\-.*',  # Double dashes
        r'.*\.\..*',  # Double dots
    ]
    
    for pattern in invalid_patterns:
        if re.match(pattern, symbol):
            return False
    
    return True


def normalize_fund_symbol(symbol: str) -> Optional[str]:
    """Normalize fund symbol to standard format"""
    if not validate_fund_symbol(symbol):
        return None
    
    # Convert to uppercase and strip whitespace
    normalized = symbol.strip().upper()
    
    # Remove any invalid characters that might have slipped through
    normalized = re.sub(r'[^A-Z0-9\-\.]', '', normalized)
    
    return normalized if normalized else None


def parse_filing_date(date_str: str) -> Optional[datetime]:
    """Parse various date formats commonly found in SEC filings"""
    if not date_str:
        return None
    
    # Common date formats in SEC filings
    date_formats = [
        '%Y-%m-%d',      # 2024-03-15
        '%m/%d/%Y',      # 03/15/2024
        '%m-%d-%Y',      # 03-15-2024
        '%Y%m%d',        # 20240315
        '%B %d, %Y',     # March 15, 2024
        '%b %d, %Y',     # Mar 15, 2024
        '%d-%b-%Y',      # 15-Mar-2024
    ]
    
    date_str = date_str.strip()
    
    for fmt in date_formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    return None


def validate_url(url: str) -> bool:
    """Validate if a string is a proper URL"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def is_sec_url(url: str) -> bool:
    """Check if URL is from SEC domain"""
    try:
        parsed = urlparse(url)
        sec_domains = ['sec.gov', 'www.sec.gov', 'data.sec.gov']
        return parsed.netloc.lower() in sec_domains
    except Exception:
        return False


def extract_cik_from_url(url: str) -> Optional[str]:
    """Extract CIK from SEC URL if present"""
    try:
        # Pattern to match CIK in SEC URLs
        cik_pattern = r'/CIK(\d{10})'
        match = re.search(cik_pattern, url)
        if match:
            return match.group(1)
        
        # Alternative pattern for data URLs
        data_pattern = r'/data/(\d+)/'
        match = re.search(data_pattern, url)
        if match:
            return match.group(1).zfill(10)
        
        return None
    except Exception:
        return None


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"


def sanitize_text(text: str, max_length: int = None) -> str:
    """Sanitize text for safe storage and display"""
    if not text:
        return ""
    
    # Remove or replace problematic characters
    sanitized = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f]', '', text)
    
    # Normalize whitespace
    sanitized = ' '.join(sanitized.split())
    
    # Truncate if needed
    if max_length and len(sanitized) > max_length:
        sanitized = sanitized[:max_length-3] + "..."
    
    return sanitized


def create_summary_report(data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Create a summary report from download data"""
    if not data:
        return {
            'total_files': 0,
            'total_size': 0,
            'success_rate': 0.0,
            'file_types': {},
            'fund_symbols': []
        }
    
    total_files = len(data)
    successful_downloads = sum(1 for item in data if item.get('success', False))
    total_size = sum(item.get('file_size', 0) for item in data if item.get('success', False))
    
    # Count file types
    file_types = {}
    fund_symbols = set()
    
    for item in data:
        if item.get('success', False):
            # Extract file extension
            file_path = item.get('file_path', '')
            if '.' in file_path:
                ext = file_path.split('.')[-1].upper()
                file_types[ext] = file_types.get(ext, 0) + 1
            
            # Collect fund symbols
            symbol = item.get('fund_symbol')
            if symbol:
                fund_symbols.add(symbol)
    
    return {
        'total_files': total_files,
        'successful_downloads': successful_downloads,
        'failed_downloads': total_files - successful_downloads,
        'success_rate': (successful_downloads / total_files * 100) if total_files > 0 else 0.0,
        'total_size': total_size,
        'total_size_formatted': format_file_size(total_size),
        'file_types': file_types,
        'unique_fund_symbols': len(fund_symbols),
        'fund_symbols': sorted(list(fund_symbols))
    }


def get_form_type_description(form_type: str) -> str:
    """Get human-readable description of SEC form types"""
    form_descriptions = {
        '497': 'Definitive materials filed under paragraph (a), (b), (c), (d), (e) or (f) of Securities Act Rule 497',
        '497K': 'Summary Prospectus for certain open-end management investment companies filed pursuant to Securities Act Rule 497(K)',
        'N-1A': 'Registration statement filed on Form N-1A for open-end management investment companies',
        '485APOS': 'Post-effective amendment filed under the Securities Act Rule 485(a)',
        '485BPOS': 'Post-effective amendment filed under the Securities Act Rule 485(b)',
        'N-CSR': 'Certified annual shareholder report of registered management investment companies',
        'N-Q': 'Quarterly holdings report by registered management investment company',
        'DEF 14A': 'Definitive proxy statement',
        '10-K': 'Annual report pursuant to Section 13 or 15(d) of the Securities Exchange Act of 1934',
        '10-Q': 'Quarterly report pursuant to Section 13 or 15(d) of the Securities Exchange Act of 1934'
    }
    
    return form_descriptions.get(form_type, f'SEC Form {form_type}')


def log_performance_metrics(func_name: str, start_time: datetime, end_time: datetime, 
                          additional_info: Dict[str, Any] = None):
    """Log performance metrics for operations"""
    logger = logging.getLogger(__name__)
    
    duration = (end_time - start_time).total_seconds()
    
    metrics = {
        'function': func_name,
        'duration_seconds': round(duration, 3),
        'start_time': start_time.isoformat(),
        'end_time': end_time.isoformat()
    }
    
    if additional_info:
        metrics.update(additional_info)
    
    logger.info(f"Performance: {func_name} completed in {duration:.3f}s", extra={'metrics': metrics})


class ProgressTracker:
    """Simple progress tracking utility"""
    
    def __init__(self, total: int, description: str = "Processing"):
        self.total = total
        self.current = 0
        self.description = description
        self.logger = logging.getLogger(__name__)
        self.start_time = datetime.now()
    
    def update(self, increment: int = 1):
        """Update progress"""
        self.current += increment
        if self.total > 0:
            percentage = (self.current / self.total) * 100
            self.logger.info(f"{self.description}: {self.current}/{self.total} ({percentage:.1f}%)")
    
    def finish(self):
        """Mark as finished"""
        duration = (datetime.now() - self.start_time).total_seconds()
        self.logger.info(f"{self.description} completed: {self.current}/{self.total} in {duration:.2f}s")