"""
Vanguard-specific batch processing for multiple fund prospectuses.
Checkpoint 2: Process all Vanguard mutual funds using company_tickers_mf.json
"""

import json
import logging
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
import requests

from config.settings import settings
from src.sec_client import SECClient
from src.file_handler import FileHandler
from src.utils import ProgressTracker, normalize_fund_symbol


@dataclass
class VanguardFund:
    """Data structure for Vanguard fund information"""
    ticker: str
    cik_str: str
    title: str
    series_id: Optional[str] = None
    class_id: Optional[str] = None


@dataclass
class ProcessingResult:
    """Result of processing a single fund"""
    fund: VanguardFund
    success: bool
    file_path: Optional[str] = None
    error_message: Optional[str] = None
    file_size: Optional[int] = None
    filing_date: Optional[datetime] = None
    form_type: Optional[str] = None
    processing_time: Optional[float] = None


class VanguardFundProcessor:
    """Processes multiple Vanguard mutual funds in batch"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.sec_client = SECClient()
        self.file_handler = FileHandler()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': settings.USER_AGENT,
            'Accept': 'application/json'
        })
        
    def get_vanguard_funds(self) -> List[VanguardFund]:
        """Retrieve list of all Vanguard mutual funds from SEC JSON"""
        try:
            self.logger.info("Fetching Vanguard funds from SEC company_tickers_mf.json...")
            
            url = "https://www.sec.gov/files/company_tickers_mf.json"
            
            # Rate limit before API call
            time.sleep(settings.REQUEST_DELAY)
            response = self.session.get(url)
            
            if response.status_code != 200:
                raise Exception(f"Failed to fetch company tickers: HTTP {response.status_code}")
            
            data = response.json()
            vanguard_funds = []
            
            # The data structure is: {"fields": ["cik", "seriesId", "classId", "symbol"], "data": [...]}
            if 'fields' not in data or 'data' not in data:
                raise Exception("Unexpected data structure from SEC API")
            
            fields = data['fields']  # ["cik", "seriesId", "classId", "symbol"]
            
            # Process each fund record
            for record in data['data']:
                if len(record) >= 4:
                    cik, series_id, class_id, symbol = record[:4]
                    
                    # Identify Vanguard funds by ticker pattern
                    if self._is_vanguard_fund_by_ticker(symbol):
                        fund = VanguardFund(
                            ticker=symbol,
                            cik_str=str(cik).zfill(10),
                            title=f"Vanguard {symbol}",  # We don't have full title from this data
                            series_id=series_id,
                            class_id=class_id
                        )
                        vanguard_funds.append(fund)
            
            self.logger.info(f"Found {len(vanguard_funds)} Vanguard mutual funds")
            
            # Sort by ticker for consistent processing order
            vanguard_funds.sort(key=lambda x: x.ticker)
            
            return vanguard_funds
            
        except Exception as e:
            self.logger.error(f"Error fetching Vanguard funds: {str(e)}")
            raise
    
    def _is_vanguard_fund_by_ticker(self, ticker: str) -> bool:
        """Determine if a fund is a Vanguard fund based on ticker pattern"""
        if not ticker or len(ticker) != 5:
            return False
            
        # Vanguard mutual fund pattern: starts with V and ends with X
        if ticker.startswith('V') and ticker.endswith('X'):
            return True
            
        return False
    
    def _is_vanguard_fund(self, title: str, ticker: str) -> bool:
        """Determine if a fund is a Vanguard fund based on title and ticker (legacy method)"""
        vanguard_indicators = [
            'VANGUARD',
            'VG ',  # Short for Vanguard
            'ADMIRAL',  # Vanguard Admiral shares
        ]
        
        # Check title for Vanguard indicators
        for indicator in vanguard_indicators:
            if indicator in title:
                return True
        
        # Check ticker patterns (Vanguard tickers often start with V)
        if ticker and len(ticker) >= 4:
            # Many Vanguard funds start with V and end with X
            if ticker.startswith('V') and ticker.endswith('X'):
                return True
            # Some Vanguard funds follow VXXXX pattern
            if ticker.startswith('V') and len(ticker) == 5:
                return True
        
        return False
    
    def process_all_funds(self, max_funds: Optional[int] = None, 
                         skip_existing: bool = True) -> List[ProcessingResult]:
        """Process all Vanguard funds and retrieve their prospectuses"""
        try:
            # Get list of Vanguard funds
            vanguard_funds = self.get_vanguard_funds()
            
            if max_funds:
                vanguard_funds = vanguard_funds[:max_funds]
                self.logger.info(f"Limited to first {max_funds} funds for testing")
            
            self.logger.info(f"Starting batch processing of {len(vanguard_funds)} Vanguard funds")
            
            # Initialize progress tracking
            progress = ProgressTracker(len(vanguard_funds), "Processing Vanguard funds")
            results = []
            
            start_time = datetime.now()
            
            for i, fund in enumerate(vanguard_funds):
                self.logger.info(f"\n--- Processing fund {i+1}/{len(vanguard_funds)}: {fund.ticker} ---")
                
                # Process individual fund
                result = self._process_single_fund(fund, skip_existing)
                results.append(result)
                
                # Update progress
                progress.update()
                
                # Log result
                if result.success:
                    if result.file_size:
                        self.logger.info(f" {fund.ticker}: Success - {result.file_size:,} bytes")
                    else:
                        self.logger.info(f" {fund.ticker}: Success - {result.error_message}")
                else:
                    self.logger.warning(f" {fund.ticker}: Failed - {result.error_message}")
                
                # Rate limiting between funds
                if i < len(vanguard_funds) - 1:  # Don't sleep after last fund
                    time.sleep(settings.REQUEST_DELAY * 2)  # Extra delay for batch processing
            
            progress.finish()
            
            # Generate comprehensive summary
            self._log_batch_summary(results, start_time)
            
            # Save detailed results
            self._save_batch_results(results)
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error in batch processing: {str(e)}")
            raise
    
    def _process_single_fund(self, fund: VanguardFund, skip_existing: bool) -> ProcessingResult:
        """Process a single fund and return result"""
        start_time = time.time()
        
        try:
            # Check if fund already exists
            if skip_existing:
                existing_file = self.file_handler.get_existing_prospectus(fund.ticker)
                if existing_file:
                    self.logger.info(f"Skipping {fund.ticker} - already exists: {existing_file.name}")
                    return ProcessingResult(
                        fund=fund,
                        success=True,
                        file_path=str(existing_file),
                        error_message="Skipped - file already exists",
                        processing_time=time.time() - start_time
                    )
            
            # Validate fund symbol
            normalized_ticker = normalize_fund_symbol(fund.ticker)
            if not normalized_ticker:
                return ProcessingResult(
                    fund=fund,
                    success=False,
                    error_message=f"Invalid ticker format: {fund.ticker}",
                    processing_time=time.time() - start_time
                )
            
            # Retrieve prospectus
            prospectus_data = self.sec_client.get_latest_prospectus(normalized_ticker)
            
            if not prospectus_data:
                return ProcessingResult(
                    fund=fund,
                    success=False,
                    error_message="No prospectus found",
                    processing_time=time.time() - start_time
                )
            
            # Save prospectus
            saved_path = self.file_handler.save_prospectus(prospectus_data)
            
            return ProcessingResult(
                fund=fund,
                success=True,
                file_path=str(saved_path),
                file_size=len(prospectus_data.content),
                filing_date=prospectus_data.filing_date,
                form_type=prospectus_data.form_type,
                processing_time=time.time() - start_time
            )
            
        except Exception as e:
            self.logger.error(f"Error processing {fund.ticker}: {str(e)}")
            return ProcessingResult(
                fund=fund,
                success=False,
                error_message=str(e),
                processing_time=time.time() - start_time
            )
    
    def _log_batch_summary(self, results: List[ProcessingResult], start_time: datetime):
        """Log comprehensive summary of batch processing"""
        end_time = datetime.now()
        total_time = (end_time - start_time).total_seconds()
        
        successful = [r for r in results if r.success and not (r.error_message and "already exists" in r.error_message)]
        failed = [r for r in results if not r.success]
        skipped = [r for r in results if r.success and r.error_message and "already exists" in r.error_message]
        
        total_size = sum(r.file_size or 0 for r in successful)
        avg_processing_time = sum(r.processing_time or 0 for r in results) / len(results) if results else 0
        
        self.logger.info("\n" + "="*80)
        self.logger.info(" BATCH PROCESSING SUMMARY")
        self.logger.info("="*80)
        self.logger.info(f"Total funds processed: {len(results)}")
        self.logger.info(f"Successful downloads: {len(successful)}")
        self.logger.info(f" Skipped (already exist): {len(skipped)}")
        self.logger.info(f" Failed downloads: {len(failed)}")
        self.logger.info(f" Success rate: {(len(successful) / len(results) * 100):.1f}%")
        self.logger.info(f" Total data downloaded: {self._format_file_size(total_size)}")
        self.logger.info(f" Total processing time: {total_time:.1f} seconds")
        self.logger.info(f" Average time per fund: {avg_processing_time:.2f} seconds")
        
        if failed:
            self.logger.info(f"\n Failed funds ({len(failed)}):")
            for result in failed[:10]:  # Show first 10 failures
                self.logger.info(f"  • {result.fund.ticker}: {result.error_message}")
            if len(failed) > 10:
                self.logger.info(f"  ... and {len(failed) - 10} more failures")
        
        # Form type breakdown
        form_types = {}
        for result in successful:
            if result.form_type:
                form_types[result.form_type] = form_types.get(result.form_type, 0) + 1
        
        if form_types:
            self.logger.info(f"\n Form types retrieved:")
            for form_type, count in sorted(form_types.items()):
                self.logger.info(f"  • {form_type}: {count} funds")
        
        self.logger.info("="*80)
    
    def _format_file_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    def _save_batch_results(self, results: List[ProcessingResult]):
        """Save detailed batch results to JSON file"""
        try:
            batch_results = {
                'processing_timestamp': datetime.now().isoformat(),
                'total_funds': len(results),
                'successful_downloads': sum(1 for r in results if r.success and not (r.error_message and "already exists" in r.error_message)),
                'skipped_funds': sum(1 for r in results if r.success and r.error_message and "already exists" in r.error_message),
                'failed_downloads': sum(1 for r in results if not r.success),
                'results': []
            }
            
            for result in results:
                result_data = {
                    'ticker': result.fund.ticker,
                    'title': result.fund.title,
                    'cik': result.fund.cik_str,
                    'success': result.success,
                    'file_path': result.file_path,
                    'error_message': result.error_message,
                    'file_size': result.file_size,
                    'filing_date': result.filing_date.isoformat() if result.filing_date else None,
                    'form_type': result.form_type,
                    'processing_time': result.processing_time
                }
                batch_results['results'].append(result_data)
            
            # Save to file
            results_file = settings.PROSPECTUS_DIR / 'vanguard_batch_results.json'
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(batch_results, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f" Detailed results saved to: {results_file}")
            
        except Exception as e:
            self.logger.error(f"Error saving batch results: {str(e)}")
    
    def get_processing_statistics(self, results: List[ProcessingResult]) -> Dict[str, Any]:
        """Generate detailed statistics from processing results"""
        successful = [r for r in results if r.success and not (r.error_message and "already exists" in r.error_message)]
        failed = [r for r in results if not r.success]
        skipped = [r for r in results if r.success and r.error_message and "already exists" in r.error_message]
        
        stats = {
            'total_funds': len(results),
            'successful_downloads': len(successful),
            'failed_downloads': len(failed),
            'skipped_funds': len(skipped),
            'success_rate': (len(successful) / len(results) * 100) if results else 0,
            'total_size_bytes': sum(r.file_size or 0 for r in successful),
            'average_processing_time': sum(r.processing_time or 0 for r in results) / len(results) if results else 0,
            'form_type_distribution': {},
            'error_categories': {},
            'successful_tickers': [r.fund.ticker for r in successful],
            'failed_tickers': [r.fund.ticker for r in failed]
        }
        
        # Form type distribution
        for result in successful:
            if result.form_type:
                stats['form_type_distribution'][result.form_type] = \
                    stats['form_type_distribution'].get(result.form_type, 0) + 1
        
        # Error categorization
        for result in failed:
            error_category = self._categorize_error(result.error_message or "Unknown error")
            stats['error_categories'][error_category] = \
                stats['error_categories'].get(error_category, 0) + 1
        
        return stats
    
    def _categorize_error(self, error_message: str) -> str:
        """Categorize error messages for analysis"""
        error_message = error_message.lower()
        
        if 'cik' in error_message or 'not found' in error_message:
            return 'CIK_NOT_FOUND'
        elif 'no prospectus' in error_message or 'no filings' in error_message:
            return 'NO_PROSPECTUS'
        elif 'network' in error_message or 'timeout' in error_message or 'connection' in error_message:
            return 'NETWORK_ERROR'
        elif 'rate limit' in error_message or '429' in error_message:
            return 'RATE_LIMITED'
        elif 'invalid' in error_message or 'format' in error_message:
            return 'INVALID_DATA'
        else:
            return 'OTHER'