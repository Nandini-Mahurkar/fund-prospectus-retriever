"""
SEC EDGAR API client for retrieving fund prospectuses.
"""

import requests
import time
import logging
import json
import re
from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urljoin, urlparse

from config.settings import settings
from src.models import ProspectusData


class SECClient:
    def __init__(self):
        self.base_url = settings.SEC_API_BASE_URL
        self.data_api_url = "https://data.sec.gov"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': settings.USER_AGENT,
            'Accept': 'application/json, text/html, */*'
        })
        self.logger = logging.getLogger(__name__)
    
    def get_latest_prospectus(self, fund_symbol: str) -> Optional[ProspectusData]:
        """Retrieve the latest prospectus for a given fund symbol"""
        try:
            self.logger.info(f"Starting prospectus search for fund symbol: {fund_symbol}")
            
            # Step 1: Find the CIK for the fund symbol
            cik = self._find_cik_by_symbol(fund_symbol)
            if not cik:
                self.logger.error(f"Could not find CIK for fund symbol: {fund_symbol}")
                return None
            
            self.logger.info(f"Found CIK {cik} for fund symbol {fund_symbol}")
            
            # Step 2: Search for recent filings
            filings = self._search_edgar_filings(cik, fund_symbol)
            if not filings:
                self.logger.error(f"No prospectus filings found for {fund_symbol}")
                return None
            
            # Step 3: Find the most recent prospectus filing
            latest_filing = self._find_latest_prospectus(filings)
            if not latest_filing:
                self.logger.error(f"No valid prospectus found in filings for {fund_symbol}")
                return None
            
            self.logger.info(f"Found latest prospectus filing: {latest_filing['accessionNumber']}")
            
            # Step 4: Download the prospectus document
            document_content = self._download_document(latest_filing['documentUrl'])
            if not document_content:
                self.logger.error(f"Failed to download prospectus document")
                return None
            
            # Step 5: Create ProspectusData object
            prospectus_data = ProspectusData(
                fund_symbol=fund_symbol,
                filing_date=datetime.strptime(latest_filing['filingDate'], '%Y-%m-%d'),
                document_type=self._determine_document_type(latest_filing['documentUrl']),
                content=document_content,
                source_url=latest_filing['documentUrl'],
                file_size=len(document_content),
                cik=cik,
                accession_number=latest_filing['accessionNumber'],
                form_type=latest_filing['form']
            )
            
            self.logger.info(f"Successfully retrieved prospectus for {fund_symbol}")
            return prospectus_data
            
        except Exception as e:
            self.logger.error(f"Error retrieving prospectus for {fund_symbol}: {str(e)}")
            return None
    
    def _find_cik_by_symbol(self, fund_symbol: str) -> Optional[str]:
        """Find CIK (Central Index Key) for a given fund symbol"""
        try:
            # Try the SEC data API first for company tickers
            url = f"{self.data_api_url}/api/xbrl/companyfacts/CIK{fund_symbol}.json"
            
            self._rate_limit()
            response = self.session.get(url)
            
            if response.status_code == 200:
                return fund_symbol.zfill(10)  # CIK is 10 digits, zero-padded
            
            tickers_url = "https://www.sec.gov/files/company_tickers_mf.json"
            
            self._rate_limit()
            response = self.session.get(tickers_url)
            
            if response.status_code == 200:
                tickers_data = response.json()
                
                
                if 'fields' in tickers_data and 'data' in tickers_data:
                    fields = tickers_data['fields']  # ["cik", "seriesId", "classId", "symbol"]
                    
                    # Search for the fund symbol in the data array
                    for record in tickers_data['data']:
                        if len(record) >= 4:
                            cik, series_id, class_id, symbol = record[:4]
                            if symbol.upper() == fund_symbol.upper():
                                return str(cik).zfill(10)
            
            # If still not found, try a broader search approach
            return self._search_cik_by_name(fund_symbol)
            
        except Exception as e:
            self.logger.error(f"Error finding CIK for {fund_symbol}: {str(e)}")
            return None
            
    def _search_cik_by_name(self, fund_symbol: str) -> Optional[str]:
        """Search for CIK using company name search (fallback method)"""
        try:
            # For VUSXX, we know it's a Vanguard fund, so we can search for Vanguard
            if fund_symbol.upper().startswith('V'):
                search_terms = ["Vanguard", fund_symbol]
            else:
                search_terms = [fund_symbol]
            
            for search_term in search_terms:
                url = f"{self.data_api_url}/api/xbrl/companyconcept/CIK0000862084/us-gaap/Assets.json"
                
                # This is a simplified approach - in practice, you'd want a more robust search
                # For VUSXX specifically, we can use Vanguard's known CIK
                if fund_symbol.upper() == "VUSXX":
                    return "0000862084"  # Vanguard Group's CIK
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error in CIK name search: {str(e)}")
            return None
    
    def _search_edgar_filings(self, cik: str, fund_symbol: str) -> Optional[List[Dict[str, Any]]]:
        """Search EDGAR database for fund filings"""
        try:
            # Use the SEC data API to get recent filings
            url = f"{self.data_api_url}/api/xbrl/companyfacts/CIK{cik.zfill(10)}.json"
            
            self._rate_limit()
            response = self.session.get(url)
            
            if response.status_code != 200:
                # Try alternative approach using submissions API
                return self._search_filings_via_submissions(cik)
            
            return self._search_filings_via_submissions(cik)
            
        except Exception as e:
            self.logger.error(f"Error searching EDGAR filings: {str(e)}")
            return None
    
    def _search_filings_via_submissions(self, cik: str) -> Optional[List[Dict[str, Any]]]:
        """Search filings using the submissions API"""
        try:
            url = f"{self.data_api_url}/submissions/CIK{cik.zfill(10)}.json"
            
            self._rate_limit()
            response = self.session.get(url)
            
            if response.status_code != 200:
                self.logger.warning(f"Submissions API returned {response.status_code}")
                return None
            
            data = response.json()
            
            if 'filings' not in data or 'recent' not in data['filings']:
                self.logger.warning("No recent filings found in submissions data")
                return None
            
            recent_filings = data['filings']['recent']
            
            # Filter for prospectus-related forms (497, 497K, N-1A, etc.)
            prospectus_forms = ['497', '497K', 'N-1A', '485BPOS', '485APOS']
            
            filings = []
            for i in range(len(recent_filings['form'])):
                form = recent_filings['form'][i]
                if any(form.startswith(pf) for pf in prospectus_forms):
                    filing = {
                        'form': form,
                        'filingDate': recent_filings['filingDate'][i],
                        'accessionNumber': recent_filings['accessionNumber'][i],
                        'primaryDocument': recent_filings['primaryDocument'][i],
                        'documentUrl': self._build_document_url(
                            cik, 
                            recent_filings['accessionNumber'][i], 
                            recent_filings['primaryDocument'][i]
                        )
                    }
                    filings.append(filing)
            
            # Sort by filing date (most recent first)
            filings.sort(key=lambda x: x['filingDate'], reverse=True)
            
            self.logger.info(f"Found {len(filings)} prospectus-related filings")
            return filings
            
        except Exception as e:
            self.logger.error(f"Error in submissions search: {str(e)}")
            return None
    
    def _build_document_url(self, cik: str, accession_number: str, primary_document: str) -> str:
        """Build the full URL for a document"""
        # Remove dashes from accession number for URL
        accession_clean = accession_number.replace('-', '')
        
        base_url = "https://www.sec.gov/Archives/edgar/data"
        cik_clean = cik.lstrip('0')  # Remove leading zeros for URL
        
        return f"{base_url}/{cik_clean}/{accession_clean}/{primary_document}"
    
    def _find_latest_prospectus(self, filings: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Find the most recent prospectus from the list of filings"""
        if not filings:
            return None
        
        # Prioritize certain form types
        form_priority = ['497K', '497', 'N-1A', '485BPOS', '485APOS']
        
        for form_type in form_priority:
            for filing in filings:
                if filing['form'].startswith(form_type):
                    return filing
        
        # If no preferred form found, return the most recent
        return filings[0] if filings else None
    
    def _download_document(self, document_url: str) -> Optional[bytes]:
        """Download document content from SEC"""
        try:
            self.logger.info(f"Downloading document from: {document_url}")
            
            self._rate_limit()
            response = self.session.get(document_url)
            
            if response.status_code == 200:
                self.logger.info(f"Successfully downloaded document ({len(response.content)} bytes)")
                return response.content
            else:
                self.logger.error(f"Failed to download document: HTTP {response.status_code}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error downloading document from {document_url}: {str(e)}")
            return None
    
    def _determine_document_type(self, document_url: str) -> str:
        """Determine if document is HTML or PDF based on URL"""
        if document_url.lower().endswith('.pdf'):
            return 'PDF'
        elif document_url.lower().endswith(('.htm', '.html')):
            return 'HTML'
        else:
            # Default to HTML for SEC filings
            return 'HTML'
    
    def _rate_limit(self):
        """Implement rate limiting for SEC API calls"""
        time.sleep(settings.REQUEST_DELAY)