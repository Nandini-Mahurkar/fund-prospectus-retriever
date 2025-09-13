"""
Generic fund processor for arbitrary fund retrieval.
Checkpoint 3: Handle any fund symbol (ETFs, mutual funds, etc.)
"""

import json
import logging
import time
import re
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
import requests

from config.settings import settings
from src.sec_client import SECClient
from src.file_handler import FileHandler
from src.utils import ProgressTracker, normalize_fund_symbol


@dataclass
class FundInfo:
    """Generic data structure for fund information"""
    ticker: str
    cik_str: Optional[str] = None
    title: Optional[str] = None
    fund_type: Optional[str] = None  # 'ETF', 'MUTUAL_FUND', 'CLOSED_END', etc.
    provider: Optional[str] = None   # 'Vanguard', 'Invesco', 'SPDR', etc.
    series_id: Optional[str] = None
    class_id: Optional[str] = None


@dataclass
class RetrievalResult:
    """Result of attempting to retrieve a fund prospectus"""
    fund: FundInfo
    success: bool
    file_path: Optional[str] = None
    error_message: Optional[str] = None
    error_category: Optional[str] = None
    file_size: Optional[int] = None
    filing_date: Optional[datetime] = None
    form_type: Optional[str] = None
    processing_time: Optional[float] = None
    discovery_method: Optional[str] = None  # How we found the fund
    supplements_found: int = 0


class GenericFundProcessor:
    """Processes arbitrary fund symbols using multiple discovery strategies"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.sec_client = SECClient()
        self.file_handler = FileHandler()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': settings.USER_AGENT,
            'Accept': 'application/json'
        })
        
        # Cache for company tickers to avoid repeated API calls
        self._tickers_cache = None
        self._company_tickers_cache = None
        
    def retrieve_fund_prospectus(self, fund_symbol: str) -> RetrievalResult:
        """Retrieve prospectus for any fund symbol using multiple strategies"""
        start_time = time.time()
        
        try:
            # Normalize and validate fund symbol
            normalized_symbol = normalize_fund_symbol(fund_symbol)
            if not normalized_symbol:
                return RetrievalResult(
                    fund=FundInfo(ticker=fund_symbol),
                    success=False,
                    error_message=f"Invalid fund symbol format: {fund_symbol}",
                    error_category="INVALID_SYMBOL",
                    processing_time=time.time() - start_time
                )
            
            self.logger.info(f"Starting arbitrary fund retrieval for: {normalized_symbol}")
            
            # Step 1: Discover fund information using multiple strategies
            fund_info = self._discover_fund_info(normalized_symbol)
            
            if not fund_info or not fund_info.cik_str:
                return RetrievalResult(
                    fund=FundInfo(ticker=normalized_symbol),
                    success=False,
                    error_message="Could not discover fund information or CIK",
                    error_category="DISCOVERY_FAILED",
                    processing_time=time.time() - start_time
                )
            
            self.logger.info(f"Discovered fund: {fund_info.title or 'Unknown'} (CIK: {fund_info.cik_str})")
            
            # Step 2: Retrieve prospectus using SEC client with discovered CIK
            prospectus_data = self.sec_client.get_latest_prospectus(
                normalized_symbol, 
                known_cik=fund_info.cik_str
            )
            
            if not prospectus_data:
                return RetrievalResult(
                    fund=fund_info,
                    success=False,
                    error_message="No prospectus found despite successful fund discovery",
                    error_category="NO_PROSPECTUS",
                    discovery_method=fund_info.provider,
                    processing_time=time.time() - start_time
                )
            
            # Step 3: Save prospectus
            saved_path = self.file_handler.save_prospectus(prospectus_data)
            
            return RetrievalResult(
                fund=fund_info,
                success=True,
                file_path=str(saved_path),
                file_size=len(prospectus_data.content),
                filing_date=prospectus_data.filing_date,
                form_type=prospectus_data.form_type,
                discovery_method=fund_info.provider,
                processing_time=time.time() - start_time
            )
            
        except Exception as e:
            self.logger.error(f"Error processing fund {fund_symbol}: {str(e)}")
            return RetrievalResult(
                fund=FundInfo(ticker=fund_symbol),
                success=False,
                error_message=str(e),
                error_category="PROCESSING_ERROR",
                processing_time=time.time() - start_time
            )
    
    def _discover_fund_info(self, fund_symbol: str) -> Optional[FundInfo]:
        """Discover fund information using multiple strategies"""
        
        # Strategy 1: Check mutual fund tickers JSON
        fund_info = self._discover_from_mutual_fund_json(fund_symbol)
        if fund_info:
            fund_info.fund_type = "MUTUAL_FUND"
            return fund_info
        
        # Strategy 2: Check ETF listings  
        fund_info = self._discover_from_etf_sources(fund_symbol)
        if fund_info:
            fund_info.fund_type = "ETF"
            return fund_info
        
        # Strategy 3: Direct CIK search (in case it's a CIK)
        fund_info = self._discover_by_direct_cik(fund_symbol)
        if fund_info:
            return fund_info
        
        # Strategy 4: SEC search by company name
        fund_info = self._discover_by_sec_search(fund_symbol)
        if fund_info:
            return fund_info
        
        # Strategy 5: Pattern-based provider detection
        fund_info = self._discover_by_pattern_matching(fund_symbol)
        if fund_info:
            return fund_info
        
        return None
    
    def _discover_from_mutual_fund_json(self, fund_symbol: str) -> Optional[FundInfo]:
        """Discover fund from SEC mutual fund tickers JSON"""
        try:
            if not self._tickers_cache:
                self.logger.info("Fetching mutual fund tickers from SEC...")
                url = "https://www.sec.gov/files/company_tickers_mf.json"
                
                time.sleep(settings.REQUEST_DELAY)
                response = self.session.get(url)
                
                if response.status_code == 200:
                    self._tickers_cache = response.json()
                else:
                    self.logger.warning(f"Failed to fetch mutual fund tickers: HTTP {response.status_code}")
                    return None
            
            if 'fields' in self._tickers_cache and 'data' in self._tickers_cache:
                for record in self._tickers_cache['data']:
                    if len(record) >= 4:
                        cik, series_id, class_id, symbol = record[:4]
                        if symbol.upper() == fund_symbol.upper():
                            provider = self._determine_provider_from_cik_dynamically(str(cik))
                            return FundInfo(
                                ticker=symbol,
                                cik_str=str(cik).zfill(10),
                                title=f"{provider} {symbol}" if provider else f"Fund {symbol}",
                                provider=provider,
                                series_id=series_id,
                                class_id=class_id
                            )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error discovering from mutual fund JSON: {str(e)}")
            return None
    
    def _discover_from_etf_sources(self, fund_symbol: str) -> Optional[FundInfo]:
        """Discover ETF information using dynamic SEC searches and provider patterns"""
        try:
            symbol_upper = fund_symbol.upper()
            
            # Strategy 1: Search SEC company tickers (includes some ETFs)
            fund_info = self._search_sec_company_tickers(fund_symbol)
            if fund_info:
                return fund_info
            
            # Strategy 2: Search SEC submissions by ticker symbol
            fund_info = self._search_sec_by_ticker(fund_symbol)
            if fund_info:
                return fund_info
            
            # Strategy 3: Pattern-based provider detection + CIK lookup
            provider = self._detect_etf_provider_by_pattern(symbol_upper)
            if provider:
                cik = self._find_provider_cik_dynamically(provider)
                if cik:
                    return FundInfo(
                        ticker=fund_symbol,
                        cik_str=cik,
                        title=f"{provider} {fund_symbol} ETF",
                        provider=provider,
                        fund_type="ETF"
                    )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error discovering ETF info: {str(e)}")
            return None

    def _search_sec_company_tickers(self, fund_symbol: str) -> Optional[FundInfo]:
        """Search regular SEC company tickers (some ETFs are listed here)"""
        try:
            if not self._company_tickers_cache:
                url = "https://www.sec.gov/files/company_tickers.json"
                
                time.sleep(settings.REQUEST_DELAY)
                response = self.session.get(url)
                
                if response.status_code == 200:
                    self._company_tickers_cache = response.json()
                else:
                    self.logger.warning(f"Failed to fetch company tickers: HTTP {response.status_code}")
                    return None
            
            # Search through company tickers
            for key, company_info in self._company_tickers_cache.items():
                if isinstance(company_info, dict):
                    ticker = company_info.get('ticker', '')
                    if ticker.upper() == fund_symbol.upper():
                        cik = str(company_info.get('cik_str', '')).zfill(10)
                        title = company_info.get('title', f"Fund {ticker}")
                        
                        # Try to determine if this is an ETF based on title
                        if any(etf_indicator in title.upper() for etf_indicator in ['ETF', 'EXCHANGE TRADED', 'INDEX FUND']):
                            provider = self._extract_provider_from_title(title)
                            return FundInfo(
                                ticker=ticker,
                                cik_str=cik,
                                title=title,
                                provider=provider,
                                fund_type="ETF"
                            )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error searching SEC company tickers: {str(e)}")
            return None

    def _search_sec_by_ticker(self, fund_symbol: str) -> Optional[FundInfo]:
        """Search SEC submissions API using ticker symbol patterns"""
        try:
            # Try searching known ETF companies dynamically
            major_etf_companies = [
                "State Street", "SPDR", "BlackRock", "iShares", 
                "Vanguard", "Invesco", "Fidelity", "Schwab"
            ]
            
            for company_name in major_etf_companies:
                cik = self._find_company_cik_by_name(company_name)
                if cik:
                    # Check if this company has filings for our symbol
                    if self._check_company_has_fund(cik, fund_symbol):
                        provider = self._normalize_provider_name(company_name)
                        return FundInfo(
                            ticker=fund_symbol,
                            cik_str=cik,
                            title=f"{provider} {fund_symbol} ETF",
                            provider=provider,
                            fund_type="ETF"
                        )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error in SEC ticker search: {str(e)}")
            return None

    def _find_company_cik_by_name(self, company_name: str) -> Optional[str]:
        """Find CIK for a company by searching SEC data"""
        try:
            if not self._company_tickers_cache:
                url = "https://www.sec.gov/files/company_tickers.json"
                
                time.sleep(settings.REQUEST_DELAY)
                response = self.session.get(url)
                
                if response.status_code == 200:
                    self._company_tickers_cache = response.json()
                else:
                    return None
            
            for key, company_info in self._company_tickers_cache.items():
                if isinstance(company_info, dict):
                    title = company_info.get('title', '').upper()
                    if company_name.upper() in title:
                        return str(company_info.get('cik_str', '')).zfill(10)
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error finding CIK for {company_name}: {str(e)}")
            return None

    def _find_provider_cik_dynamically(self, provider: str) -> Optional[str]:
        """Dynamically find CIK for a provider using SEC APIs"""
        try:
            # Map provider names to their likely SEC company names
            provider_search_terms = {
                'SPDR': ['State Street', 'SPDR'],
                'iShares': ['BlackRock', 'iShares'],
                'Vanguard': ['Vanguard'],
                'Invesco': ['Invesco'],
                'Fidelity': ['Fidelity'],
                'Schwab': ['Schwab', 'Charles Schwab'],
                'ARK': ['ARK Investment'],
                'ProShares': ['ProShares']
            }
            
            search_terms = provider_search_terms.get(provider, [provider])
            
            for term in search_terms:
                cik = self._find_company_cik_by_name(term)
                if cik:
                    return cik
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error finding CIK for provider {provider}: {str(e)}")
            return None

    def _check_company_has_fund(self, cik: str, fund_symbol: str) -> bool:
        """Check if a company has filings related to a specific fund symbol"""
        try:
            # Try to get recent submissions and look for the fund symbol
            url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
            
            time.sleep(settings.REQUEST_DELAY)
            response = self.session.get(url)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check recent filings for the fund symbol
                if 'filings' in data and 'recent' in data['filings']:
                    recent = data['filings']['recent']
                    
                    # Look through primary documents for fund symbol
                    for i, doc in enumerate(recent.get('primaryDocument', [])):
                        if fund_symbol.upper() in doc.upper():
                            return True
                    
                    # Also check form descriptions/titles if available
                    for i, form in enumerate(recent.get('form', [])):
                        if form in ['497', '497K', 'N-1A']:  # Fund-related forms
                            return True  # Assume this company files fund documents
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking if company {cik} has fund {fund_symbol}: {str(e)}")
            return False

    def _extract_provider_from_title(self, title: str) -> Optional[str]:
        """Extract provider name from SEC filing title"""
        title_upper = title.upper()
        
        provider_indicators = {
            'VANGUARD': 'Vanguard',
            'SPDR': 'SPDR',
            'STATE STREET': 'SPDR',
            'BLACKROCK': 'iShares',
            'ISHARES': 'iShares',
            'INVESCO': 'Invesco',
            'FIDELITY': 'Fidelity',
            'SCHWAB': 'Schwab',
            'ARK': 'ARK',
            'PROSHARES': 'ProShares'
        }
        
        for indicator, provider in provider_indicators.items():
            if indicator in title_upper:
                return provider
        
        return None

    def _normalize_provider_name(self, company_name: str) -> str:
        """Normalize company name to standard provider name"""
        company_upper = company_name.upper()
        
        if 'STATE STREET' in company_upper or 'SPDR' in company_upper:
            return 'SPDR'
        elif 'BLACKROCK' in company_upper or 'ISHARES' in company_upper:
            return 'iShares'
        elif 'VANGUARD' in company_upper:
            return 'Vanguard'
        elif 'INVESCO' in company_upper:
            return 'Invesco'
        elif 'FIDELITY' in company_upper:
            return 'Fidelity'
        elif 'SCHWAB' in company_upper:
            return 'Schwab'
        elif 'ARK' in company_upper:
            return 'ARK'
        elif 'PROSHARES' in company_upper:
            return 'ProShares'
        else:
            return company_name

    def _detect_etf_provider_by_pattern(self, symbol: str) -> Optional[str]:
        """Detect ETF provider based on ticker patterns (no hardcoded CIKs)"""
        
        # Common ETF ticker patterns - these are industry standards
        if symbol.startswith(('SPY', 'XL', 'GLD')):
            return 'SPDR'
        elif symbol.startswith(('IWM', 'EFA', 'IEF', 'IJH', 'IJR')):
            return 'iShares'  
        elif symbol.startswith('V') and len(symbol) == 3:  # VTI, VOO, VEA, etc.
            return 'Vanguard'
        elif symbol in ['QQQ', 'QQQM'] or symbol.startswith('PFF'):
            return 'Invesco'
        elif symbol.startswith(('ARK', 'ARKK', 'ARKQ')):
            return 'ARK'
        elif symbol.startswith(('SCH', 'SCHW')):
            return 'Schwab'
        
        return None
    
    def _discover_by_direct_cik(self, fund_symbol: str) -> Optional[FundInfo]:
        """Try to use the symbol as a direct CIK"""
        try:
            # Check if the symbol could be a CIK (numeric)
            if fund_symbol.isdigit() and len(fund_symbol) <= 10:
                cik = fund_symbol.zfill(10)
                
                # Try to validate this CIK exists
                url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
                time.sleep(settings.REQUEST_DELAY)
                response = self.session.get(url)
                
                if response.status_code == 200:
                    data = response.json()
                    entity_name = data.get('entityName', f"Company {cik}")
                    
                    return FundInfo(
                        ticker=fund_symbol,
                        cik_str=cik,
                        title=entity_name,
                        provider=self._determine_provider_from_cik_dynamically(cik)
                    )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error in direct CIK discovery: {str(e)}")
            return None
    
    def _discover_by_sec_search(self, fund_symbol: str) -> Optional[FundInfo]:
        """Attempt to discover fund through SEC company search"""
        try:
            # This is a placeholder for more advanced SEC search
            # In a full implementation, you might use SEC's EDGAR search APIs
            # or web scraping of their search interface
            
            self.logger.debug(f"SEC search not yet implemented for {fund_symbol}")
            return None
            
        except Exception as e:
            self.logger.error(f"Error in SEC search: {str(e)}")
            return None
    
    def _discover_by_pattern_matching(self, fund_symbol: str) -> Optional[FundInfo]:
        """Last resort: pattern-based discovery with dynamic CIK lookup"""
        try:
            symbol_upper = fund_symbol.upper()
            
            # Vanguard patterns
            if ((symbol_upper.startswith('V') and symbol_upper.endswith('X') and len(symbol_upper) == 5) or
                (symbol_upper.startswith('V') and len(symbol_upper) == 3)):
                
                cik = self._find_provider_cik_dynamically('Vanguard')
                if cik:
                    return FundInfo(
                        ticker=fund_symbol,
                        cik_str=cik,
                        title=f"Vanguard {fund_symbol}",
                        provider="Vanguard",
                        fund_type="ETF" if len(symbol_upper) == 3 else "MUTUAL_FUND"
                    )
            
            # Fidelity patterns
            if symbol_upper.startswith('F') and symbol_upper.endswith('X') and len(symbol_upper) == 5:
                cik = self._find_provider_cik_dynamically('Fidelity')
                if cik:
                    return FundInfo(
                        ticker=fund_symbol,
                        cik_str=cik,
                        title=f"Fidelity {fund_symbol}",
                        provider="Fidelity",
                        fund_type="MUTUAL_FUND"
                    )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error in pattern matching: {str(e)}")
            return None
    
    def _determine_provider_from_cik_dynamically(self, cik: str) -> Optional[str]:
        """Determine fund provider from CIK by looking up company name"""
        try:
            # First try to get company name from companyfacts API
            url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik.zfill(10)}.json"
            time.sleep(settings.REQUEST_DELAY)
            response = self.session.get(url)
            
            if response.status_code == 200:
                data = response.json()
                entity_name = data.get('entityName', '').upper()
                
                # Extract provider from entity name
                if 'VANGUARD' in entity_name:
                    return 'Vanguard'
                elif 'FIDELITY' in entity_name:
                    return 'Fidelity'
                elif 'STATE STREET' in entity_name or 'SPDR' in entity_name:
                    return 'SPDR'
                elif 'BLACKROCK' in entity_name or 'ISHARES' in entity_name:
                    return 'iShares'
                elif 'INVESCO' in entity_name:
                    return 'Invesco'
                elif 'SCHWAB' in entity_name:
                    return 'Schwab'
                elif 'ARK' in entity_name:
                    return 'ARK'
                elif 'PROSHARES' in entity_name:
                    return 'ProShares'
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error determining provider for CIK {cik}: {str(e)}")
            return None
    
    def process_multiple_funds(self, fund_symbols: List[str], 
                              skip_existing: bool = True) -> List[RetrievalResult]:
        """Process multiple arbitrary fund symbols"""
        try:
            self.logger.info(f"Starting batch processing of {len(fund_symbols)} arbitrary funds")
            
            # Initialize progress tracking
            progress = ProgressTracker(len(fund_symbols), "Processing arbitrary funds")
            results = []
            
            start_time = datetime.now()
            
            for i, symbol in enumerate(fund_symbols):
                self.logger.info(f"\n--- Processing fund {i+1}/{len(fund_symbols)}: {symbol} ---")
                
                # Check if fund already exists
                if skip_existing:
                    existing_file = self.file_handler.get_existing_prospectus(symbol)
                    if existing_file:
                        self.logger.info(f"Skipping {symbol} - already exists: {existing_file.name}")
                        result = RetrievalResult(
                            fund=FundInfo(ticker=symbol),
                            success=True,
                            file_path=str(existing_file),
                            error_message="Skipped - file already exists",
                            processing_time=0.0
                        )
                        results.append(result)
                        progress.update()
                        continue
                
                # Process individual fund
                result = self.retrieve_fund_prospectus(symbol)
                results.append(result)
                
                # Update progress
                progress.update()
                
                # Log result
                if result.success:
                    if result.file_size:
                        self.logger.info(f" {symbol}: Success - {result.file_size:,} bytes ({result.discovery_method})")
                    else:
                        self.logger.info(f" {symbol}: Success - {result.error_message}")
                else:
                    self.logger.warning(f" {symbol}: Failed - {result.error_message}")
                
                # Rate limiting between funds
                if i < len(fund_symbols) - 1:
                    time.sleep(settings.REQUEST_DELAY * 2)
            
            progress.finish()
            
            # Generate summary
            self._log_batch_summary(results, start_time)
            
            # Save detailed results
            self._save_batch_results(results, "arbitrary")
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error in batch processing: {str(e)}")
            raise
    
    def _log_batch_summary(self, results: List[RetrievalResult], start_time: datetime):
        """Log summary of batch processing results"""
        end_time = datetime.now()
        total_time = (end_time - start_time).total_seconds()
        
        successful = [r for r in results if r.success and not (r.error_message and "already exists" in r.error_message)]
        failed = [r for r in results if not r.success]
        skipped = [r for r in results if r.success and r.error_message and "already exists" in r.error_message]
        
        total_size = sum(r.file_size or 0 for r in successful)
        
        self.logger.info("\n" + "="*80)
        self.logger.info(" ARBITRARY FUND PROCESSING SUMMARY")
        self.logger.info("="*80)
        self.logger.info(f"Total funds processed: {len(results)}")
        self.logger.info(f"Successful downloads: {len(successful)}")
        self.logger.info(f" Skipped (already exist): {len(skipped)}")
        self.logger.info(f" Failed downloads: {len(failed)}")
        self.logger.info(f" Success rate: {(len(successful) / len(results) * 100):.1f}%")
        self.logger.info(f" Total data downloaded: {self._format_file_size(total_size)}")
        self.logger.info(f" Total processing time: {total_time:.1f} seconds")
        
        # Discovery method breakdown
        discovery_methods = {}
        for result in successful:
            method = result.discovery_method or "Unknown"
            discovery_methods[method] = discovery_methods.get(method, 0) + 1
        
        if discovery_methods:
            self.logger.info(f"\n Discovery methods used:")
            for method, count in sorted(discovery_methods.items()):
                self.logger.info(f"  • {method}: {count} funds")
        
        # Error category breakdown
        error_categories = {}
        for result in failed:
            category = result.error_category or "OTHER"
            error_categories[category] = error_categories.get(category, 0) + 1
        
        if error_categories:
            self.logger.info(f"\n Error categories:")
            for category, count in sorted(error_categories.items()):
                self.logger.info(f"  • {category}: {count} funds")
        
        self.logger.info("="*80)
    
    def _format_file_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    def _save_batch_results(self, results: List[RetrievalResult], batch_type: str):
        """Save detailed batch results to JSON file"""
        try:
            batch_results = {
                'processing_timestamp': datetime.now().isoformat(),
                'batch_type': batch_type,
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
                    'fund_type': result.fund.fund_type,
                    'provider': result.fund.provider,
                    'success': result.success,
                    'file_path': result.file_path,
                    'error_message': result.error_message,
                    'error_category': result.error_category,
                    'file_size': result.file_size,
                    'filing_date': result.filing_date.isoformat() if result.filing_date else None,
                    'form_type': result.form_type,
                    'discovery_method': result.discovery_method,
                    'processing_time': result.processing_time
                }
                batch_results['results'].append(result_data)
            
            # Save to file
            results_file = settings.PROSPECTUS_DIR / f'{batch_type}_batch_results.json'
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(batch_results, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f" Detailed results saved to: {results_file}")
            
        except Exception as e:
            self.logger.error(f"Error saving batch results: {str(e)}")

    def _discover_from_etf_sources(self, fund_symbol: str) -> Optional[FundInfo]:
        """Discover ETF information using dynamic SEC searches with proper validation"""
        try:
            symbol_upper = fund_symbol.upper()
            
            # Strategy 1: Search SEC company tickers (includes some ETFs)
            fund_info = self._search_sec_company_tickers(fund_symbol)
            if fund_info:
                return fund_info
            
            # Strategy 2: Search SEC submissions by ticker symbol
            fund_info = self._search_sec_by_ticker(fund_symbol)
            if fund_info:
                return fund_info
            
            # Strategy 3: Pattern-based provider detection + VALIDATION
            provider = self._detect_etf_provider_by_pattern(symbol_upper)
            if provider:
                cik = self._find_provider_cik_dynamically(provider)
                if cik:
                    # CRITICAL: Validate that this fund actually exists for this provider
                    if self._validate_fund_exists_for_provider(fund_symbol, cik, provider):
                        return FundInfo(
                            ticker=fund_symbol,
                            cik_str=cik,
                            title=f"{provider} {fund_symbol} ETF",
                            provider=provider,
                            fund_type="ETF"
                        )
                    else:
                        self.logger.info(f"Fund {fund_symbol} pattern matches {provider} but does not exist in their filings")
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error discovering ETF info: {str(e)}")
            return None

    def _validate_fund_exists_for_provider(self, fund_symbol: str, cik: str, provider: str) -> bool:
        """Validate that a fund symbol actually exists in a provider's SEC filings"""
        try:
            self.logger.info(f"Validating if {fund_symbol} exists in {provider} filings (CIK: {cik})")
            
            # Get recent submissions for this provider
            url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
            
            time.sleep(settings.REQUEST_DELAY)
            response = self.session.get(url)
            
            if response.status_code != 200:
                self.logger.warning(f"Could not access submissions for CIK {cik}: HTTP {response.status_code}")
                return False
            
            data = response.json()
            
            if 'filings' not in data or 'recent' not in data['filings']:
                self.logger.warning(f"No recent filings found for CIK {cik}")
                return False
            
            recent = data['filings']['recent']
            
            # Look through recent filings for this specific fund symbol
            fund_symbol_upper = fund_symbol.upper()
            
            # Check primary documents for exact fund symbol matches
            for i, doc in enumerate(recent.get('primaryDocument', [])):
                if fund_symbol_upper in doc.upper():
                    # Additional validation: check if it's a fund-related form
                    form = recent['form'][i] if i < len(recent.get('form', [])) else ''
                    if form in ['497', '497K', 'N-1A', '485BPOS', '485APOS']:
                        self.logger.info(f"Found {fund_symbol} in {provider} filings: {doc} (Form {form})")
                        return True
            
            # Check filing descriptions/report names if available
            for i, form in enumerate(recent.get('form', [])):
                if form in ['497', '497K', 'N-1A']:
                    # Look for fund symbol in associated documents
                    if i < len(recent.get('primaryDocument', [])):
                        doc = recent['primaryDocument'][i]
                        if fund_symbol_upper in doc.upper():
                            self.logger.info(f"Found {fund_symbol} reference in {provider} form {form}")
                            return True
            
            self.logger.info(f"No evidence of {fund_symbol} in {provider} recent filings")
            return False
            
        except Exception as e:
            self.logger.error(f"Error validating fund existence: {str(e)}")
            return False

    def _search_sec_by_ticker(self, fund_symbol: str) -> Optional[FundInfo]:
        """Search SEC submissions API using ticker symbol patterns with validation"""
        try:
            # Try searching known ETF companies dynamically
            major_etf_companies = [
                "State Street", "SPDR", "BlackRock", "iShares", 
                "Vanguard", "Invesco", "Fidelity", "Schwab"
            ]
            
            for company_name in major_etf_companies:
                cik = self._find_company_cik_by_name(company_name)
                if cik:
                    # ENHANCED: Check if this company has filings for our symbol
                    if self._validate_fund_exists_for_provider(fund_symbol, cik, company_name):
                        provider = self._normalize_provider_name(company_name)
                        return FundInfo(
                            ticker=fund_symbol,
                            cik_str=cik,
                            title=f"{provider} {fund_symbol} ETF",
                            provider=provider,
                            fund_type="ETF"
                        )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error in SEC ticker search: {str(e)}")
            return None

    def _detect_etf_provider_by_pattern(self, symbol: str) -> Optional[str]:
        """Detect ETF provider based on ticker patterns with stricter validation"""
        
        # Only return providers for patterns that are very reliable
        if symbol.startswith('SPY') and len(symbol) == 3:  # Only SPY, not random symbols starting with SPY
            return 'SPDR'
        elif symbol.startswith('QQQ') and len(symbol) in [3, 4]:  # QQQ, QQQM
            return 'Invesco'
        elif symbol in ['IWM', 'EFA', 'IEF', 'IJH', 'IJR', 'TLT']:  # Known iShares ETFs
            return 'iShares'
        elif symbol in ['VTI', 'VOO', 'VEA', 'BND'] and len(symbol) == 3:  # Known Vanguard 3-letter ETFs
            return 'Vanguard'
        elif symbol.startswith('XL') and len(symbol) == 3:  # SPDR sector ETFs (XLF, XLK, etc.)
            return 'SPDR'
        elif symbol == 'GLD':  # Specific known SPDR gold ETF
            return 'SPDR'
        
        # Remove catch-all patterns that were causing false positives
        return None

    def _discover_by_pattern_matching(self, fund_symbol: str) -> Optional[FundInfo]:
        """Last resort: pattern-based discovery with strict validation"""
        try:
            symbol_upper = fund_symbol.upper()
            
            # Only match very specific, reliable patterns
            
            # Vanguard mutual fund patterns (V****X)
            if (symbol_upper.startswith('V') and symbol_upper.endswith('X') and len(symbol_upper) == 5):
                cik = self._find_provider_cik_dynamically('Vanguard')
                if cik and self._validate_fund_exists_for_provider(fund_symbol, cik, 'Vanguard'):
                    return FundInfo(
                        ticker=fund_symbol,
                        cik_str=cik,
                        title=f"Vanguard {fund_symbol}",
                        provider="Vanguard",
                        fund_type="MUTUAL_FUND"
                    )
            
            # Fidelity mutual fund patterns (F****X)
            if (symbol_upper.startswith('F') and symbol_upper.endswith('X') and len(symbol_upper) == 5):
                cik = self._find_provider_cik_dynamically('Fidelity')
                if cik and self._validate_fund_exists_for_provider(fund_symbol, cik, 'Fidelity'):
                    return FundInfo(
                        ticker=fund_symbol,
                        cik_str=cik,
                        title=f"Fidelity {fund_symbol}",
                        provider="Fidelity",
                        fund_type="MUTUAL_FUND"
                    )
            
            # Do NOT provide fallback for unknown patterns
            return None
            
        except Exception as e:
            self.logger.error(f"Error in pattern matching: {str(e)}")
            return None

    def _discover_by_sec_search(self, fund_symbol: str) -> Optional[FundInfo]:
        """Enhanced SEC search with symbol validation"""
        try:
            # Check if symbol looks like a stock ticker (should be rejected)
            if self._is_likely_stock_symbol(fund_symbol):
                self.logger.info(f"{fund_symbol} appears to be a stock symbol, not a fund")
                return None
            
            # Check if symbol is obviously invalid
            if self._is_obviously_invalid_symbol(fund_symbol):
                self.logger.info(f"{fund_symbol} appears to be an invalid/test symbol")
                return None
            
            # Additional SEC search logic could go here
            return None
            
        except Exception as e:
            self.logger.error(f"Error in SEC search: {str(e)}")
            return None

    def _is_likely_stock_symbol(self, symbol: str) -> bool:
        """Check if symbol is likely a stock ticker rather than a fund"""
        
        # Known major stock symbols that aren't funds
        major_stocks = {
            'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'TSLA', 'META', 'NVDA',
            'JPM', 'JNJ', 'V', 'PG', 'HD', 'MA', 'UNH', 'DIS', 'PYPL', 'ADBE',
            'NFLX', 'CRM', 'TMO', 'ABT', 'COST', 'PFE', 'XOM', 'KO', 'PEP', 'WMT'
        }
        
        return symbol.upper() in major_stocks

    def _is_obviously_invalid_symbol(self, symbol: str) -> bool:
        """Check if symbol is obviously invalid/test data"""
        
        symbol_upper = symbol.upper()
        
        # Common test/invalid patterns
        invalid_patterns = [
            'UNKNOWN', 'FUND123', 'RANDOM', 'TEST', 'FAKE', 'INVALID', 'SAMPLE'
        ]
        
        for pattern in invalid_patterns:
            if pattern in symbol_upper:
                return True
        
        # Check for obvious test patterns (numbers, special chars, etc.)
        if any(char.isdigit() for char in symbol):
            if len([c for c in symbol if c.isdigit()]) > 2:  # More than 2 digits suggests test data
                return True
        
        return False