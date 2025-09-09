"""
Data models for fund prospectus information.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class ProspectusData:
    fund_symbol: str
    filing_date: datetime
    document_type: str  # 'HTML' or 'PDF'
    content: bytes
    source_url: str
    file_size: int
    cik: Optional[str] = None
    accession_number: Optional[str] = None
    form_type: Optional[str] = None
    
    def __post_init__(self):
        """Validate data after initialization"""
        if self.file_size != len(self.content):
            self.file_size = len(self.content)