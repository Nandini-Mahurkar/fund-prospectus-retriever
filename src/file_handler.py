"""
File handling utilities for saving and managing prospectuses.
"""

import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
import hashlib

from config.settings import settings
from src.models import ProspectusData


class FileHandler:
    def __init__(self):
        self.prospectus_dir = settings.PROSPECTUS_DIR
        self.logger = logging.getLogger(__name__)
        
        # Ensure the prospectus directory exists
        self.prospectus_dir.mkdir(parents=True, exist_ok=True)
    
    def save_prospectus(self, prospectus_data: ProspectusData) -> Path:
        """Save prospectus to local storage with metadata"""
        try:
            # Generate filename
            filename = self._generate_filename(prospectus_data)
            file_path = self.prospectus_dir / filename
            
            # Create fund-specific subdirectory
            fund_dir = self.prospectus_dir / prospectus_data.fund_symbol.upper()
            fund_dir.mkdir(exist_ok=True)
            file_path = fund_dir / filename
            
            # Save the prospectus content
            with open(file_path, 'wb') as f:
                f.write(prospectus_data.content)
            
            self.logger.info(f"Saved prospectus to: {file_path}")
            
            # Save metadata
            self._save_metadata(prospectus_data, file_path)
            
            # Log file statistics
            self.logger.info(f"File size: {file_path.stat().st_size:,} bytes")
            
            return file_path
            
        except Exception as e:
            self.logger.error(f"Error saving prospectus: {str(e)}")
            raise
    
    def _generate_filename(self, prospectus_data: ProspectusData) -> str:
        """Generate standardized filename for prospectus"""
        try:
            # Base components
            fund_symbol = prospectus_data.fund_symbol.upper()
            filing_date = prospectus_data.filing_date.strftime('%Y%m%d')
            form_type = prospectus_data.form_type or 'UNKNOWN'
            
            # Get file extension based on document type
            if prospectus_data.document_type.upper() == 'PDF':
                extension = '.pdf'
            else:
                extension = '.html'
            
            # Create unique identifier from accession number or content hash
            if prospectus_data.accession_number:
                # Use accession number (remove dashes for cleaner filename)
                unique_id = prospectus_data.accession_number.replace('-', '')
            else:
                # Fallback: create hash from content
                content_hash = hashlib.md5(prospectus_data.content).hexdigest()[:8]
                unique_id = f"hash_{content_hash}"
            
            # Construct filename: SYMBOL_FORMTYPE_YYYYMMDD_UNIQUEID.ext
            filename = f"{fund_symbol}_{form_type}_{filing_date}_{unique_id}{extension}"
            
            # Sanitize filename (remove any invalid characters)
            filename = self._sanitize_filename(filename)
            
            self.logger.debug(f"Generated filename: {filename}")
            return filename
            
        except Exception as e:
            self.logger.error(f"Error generating filename: {str(e)}")
            # Fallback filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            return f"{prospectus_data.fund_symbol}_prospectus_{timestamp}.html"
    
    def _sanitize_filename(self, filename: str) -> str:
        """Remove or replace invalid characters in filename"""
        # Replace invalid characters with underscores
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        # Remove extra underscores and ensure reasonable length
        filename = '_'.join(filter(None, filename.split('_')))
        
        # Limit filename length (keep extension)
        if len(filename) > 200:
            name_part, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
            filename = name_part[:190] + ('.' + ext if ext else '')
        
        return filename
    
    def _save_metadata(self, prospectus_data: ProspectusData, file_path: Path):
        """Save metadata alongside the prospectus file"""
        try:
            # Create metadata filename
            metadata_path = file_path.with_suffix(file_path.suffix + '.meta.json')
            
            # Prepare metadata dictionary
            metadata = {
                'fund_symbol': prospectus_data.fund_symbol,
                'filing_date': prospectus_data.filing_date.isoformat(),
                'document_type': prospectus_data.document_type,
                'source_url': prospectus_data.source_url,
                'file_size': prospectus_data.file_size,
                'form_type': prospectus_data.form_type,
                'cik': prospectus_data.cik,
                'accession_number': prospectus_data.accession_number,
                'download_timestamp': datetime.now().isoformat(),
                'local_file_path': str(file_path),
                'local_file_size': file_path.stat().st_size,
                'content_hash': hashlib.sha256(prospectus_data.content).hexdigest()
            }
            
            # Save metadata as JSON
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            self.logger.debug(f"Saved metadata to: {metadata_path}")
            
            # Also create/update a summary log file
            self._update_summary_log(prospectus_data, file_path, metadata)
            
        except Exception as e:
            self.logger.error(f"Error saving metadata: {str(e)}")
            # Don't raise - metadata failure shouldn't stop the main operation
    
    def _update_summary_log(self, prospectus_data: ProspectusData, file_path: Path, metadata: dict):
        """Update summary log with information about saved prospectuses"""
        try:
            summary_log_path = self.prospectus_dir / 'download_summary.json'
            
            # Load existing summary or create new one
            if summary_log_path.exists():
                with open(summary_log_path, 'r', encoding='utf-8') as f:
                    summary_data = json.load(f)
            else:
                summary_data = {
                    'downloads': [],
                    'last_updated': None,
                    'total_downloads': 0
                }
            
            # Add new entry
            summary_entry = {
                'fund_symbol': prospectus_data.fund_symbol,
                'filing_date': prospectus_data.filing_date.isoformat(),
                'download_timestamp': datetime.now().isoformat(),
                'form_type': prospectus_data.form_type,
                'file_path': str(file_path.relative_to(self.prospectus_dir)),
                'file_size': file_path.stat().st_size,
                'success': True
            }
            
            summary_data['downloads'].append(summary_entry)
            summary_data['last_updated'] = datetime.now().isoformat()
            summary_data['total_downloads'] = len(summary_data['downloads'])
            
            # Keep only the most recent 1000 entries to prevent file from growing too large
            if len(summary_data['downloads']) > 1000:
                summary_data['downloads'] = summary_data['downloads'][-1000:]
            
            # Save updated summary
            with open(summary_log_path, 'w', encoding='utf-8') as f:
                json.dump(summary_data, f, indent=2, ensure_ascii=False)
            
            self.logger.debug(f"Updated summary log: {summary_log_path}")
            
        except Exception as e:
            self.logger.error(f"Error updating summary log: {str(e)}")
    
    def get_existing_prospectus(self, fund_symbol: str, filing_date: datetime = None) -> Optional[Path]:
        """Check if a prospectus already exists for the given fund and date"""
        try:
            fund_dir = self.prospectus_dir / fund_symbol.upper()
            if not fund_dir.exists():
                return None
            
            # If no specific date provided, find the most recent
            if filing_date is None:
                prospectus_files = list(fund_dir.glob(f"{fund_symbol.upper()}_*"))
                if prospectus_files:
                    # Sort by modification time and return most recent
                    return max(prospectus_files, key=lambda p: p.stat().st_mtime)
                return None
            
            # Look for files matching the specific date
            date_str = filing_date.strftime('%Y%m%d')
            matching_files = list(fund_dir.glob(f"{fund_symbol.upper()}_*_{date_str}_*"))
            
            return matching_files[0] if matching_files else None
            
        except Exception as e:
            self.logger.error(f"Error checking for existing prospectus: {str(e)}")
            return None
    
    def load_metadata(self, file_path: Path) -> Optional[dict]:
        """Load metadata for a prospectus file"""
        try:
            metadata_path = file_path.with_suffix(file_path.suffix + '.meta.json')
            
            if metadata_path.exists():
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error loading metadata: {str(e)}")
            return None
    
    def cleanup_old_files(self, days_old: int = 30):
        """Remove prospectus files older than specified days"""
        try:
            cutoff_time = datetime.now().timestamp() - (days_old * 24 * 60 * 60)
            removed_count = 0
            
            for file_path in self.prospectus_dir.rglob('*'):
                if file_path.is_file() and file_path.stat().st_mtime < cutoff_time:
                    file_path.unlink()
                    removed_count += 1
                    self.logger.debug(f"Removed old file: {file_path}")
            
            if removed_count > 0:
                self.logger.info(f"Cleaned up {removed_count} old files")
            
        except Exception as e:
            self.logger.error(f"Error during cleanup: {str(e)}")