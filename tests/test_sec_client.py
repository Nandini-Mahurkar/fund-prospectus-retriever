"""
Unit tests for SEC client functionality.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import json

from src.sec_client import SECClient
from src.models import ProspectusData


class TestSECClient(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.client = SECClient()
        self.sample_fund_symbol = "VUSXX"
        self.sample_cik = "0000862084"
        
    def test_initialization(self):
        """Test SEC client initialization"""
        # Test that client is properly initialized
        self.assertIsNotNone(self.client.base_url)
        self.assertIsNotNone(self.client.data_api_url)
        self.assertIsNotNone(self.client.session)
        self.assertIsNotNone(self.client.logger)
        
        # Test session headers
        self.assertIn('User-Agent', self.client.session.headers)
        self.assertIn('Accept', self.client.session.headers)
        
        # Test URLs
        self.assertTrue(self.client.base_url.startswith('https://'))
        self.assertTrue(self.client.data_api_url.startswith('https://'))

    @patch('src.sec_client.SECClient._download_document')
    @patch('src.sec_client.SECClient._find_latest_prospectus')
    @patch('src.sec_client.SECClient._search_edgar_filings')
    @patch('src.sec_client.SECClient._find_cik_by_symbol')
    def test_get_latest_prospectus_success(self, mock_find_cik, mock_search_filings, 
                                         mock_find_latest, mock_download):
        """Test successful prospectus retrieval"""
        # Setup mocks
        mock_find_cik.return_value = self.sample_cik
        mock_search_filings.return_value = [self._create_sample_filing()]
        mock_find_latest.return_value = self._create_sample_filing()
        mock_download.return_value = b"<html>Sample prospectus content</html>"
        
        # Execute
        result = self.client.get_latest_prospectus(self.sample_fund_symbol)
        
        # Verify
        self.assertIsNotNone(result)
        self.assertIsInstance(result, ProspectusData)
        self.assertEqual(result.fund_symbol, self.sample_fund_symbol)
        self.assertEqual(result.cik, self.sample_cik)
        self.assertIsInstance(result.content, bytes)
        
        # Verify method calls
        mock_find_cik.assert_called_once_with(self.sample_fund_symbol)
        mock_search_filings.assert_called_once_with(self.sample_cik, self.sample_fund_symbol)
        mock_find_latest.assert_called_once()
        mock_download.assert_called_once()

    @patch('src.sec_client.SECClient._find_cik_by_symbol')
    def test_get_latest_prospectus_no_cik(self, mock_find_cik):
        """Test prospectus retrieval when CIK is not found"""
        # Setup
        mock_find_cik.return_value = None
        
        # Execute
        result = self.client.get_latest_prospectus(self.sample_fund_symbol)
        
        # Verify
        self.assertIsNone(result)
        mock_find_cik.assert_called_once_with(self.sample_fund_symbol)

    @patch('src.sec_client.SECClient._search_edgar_filings')
    @patch('src.sec_client.SECClient._find_cik_by_symbol')
    def test_get_latest_prospectus_no_filings(self, mock_find_cik, mock_search_filings):
        """Test prospectus retrieval when no filings are found"""
        # Setup
        mock_find_cik.return_value = self.sample_cik
        mock_search_filings.return_value = None
        
        # Execute
        result = self.client.get_latest_prospectus(self.sample_fund_symbol)
        
        # Verify
        self.assertIsNone(result)

    @patch('requests.Session.get')
    def test_find_cik_by_symbol_direct_api(self, mock_get):
        """Test CIK finding via direct API call"""
        # Setup
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        # Execute
        result = self.client._find_cik_by_symbol("0000862084")
        
        # Verify
        self.assertEqual(result, "0000862084")

    @patch('requests.Session.get')
    def test_find_cik_by_symbol_tickers_json(self, mock_get):
        """Test CIK finding via company tickers JSON"""
        # Setup mock responses
        def side_effect(url):
            mock_response = Mock()
            if 'companyfacts' in url:
                mock_response.status_code = 404
            elif 'company_tickers_mf.json' in url:
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "0": {
                        "ticker": "VUSXX",
                        "cik_str": 862084,
                        "title": "Vanguard Federal Money Market Fund"
                    }
                }
            return mock_response
        
        mock_get.side_effect = side_effect
        
        # Execute
        result = self.client._find_cik_by_symbol("VUSXX")
        
        # Verify
        self.assertEqual(result, "0000862084")

    @patch('requests.Session.get')
    def test_find_cik_by_symbol_vusxx_fallback(self, mock_get):
        """Test CIK finding for VUSXX using hardcoded fallback"""
        # Setup - make both API calls fail
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        # Execute
        result = self.client._find_cik_by_symbol("VUSXX")
        
        # Verify - should return hardcoded Vanguard CIK
        self.assertEqual(result, "0000862084")

    @patch('requests.Session.get')
    def test_search_filings_via_submissions(self, mock_get):
        """Test filing search via submissions API"""
        # Setup
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "filings": {
                "recent": {
                    "form": ["497K", "10-K", "497", "N-1A"],
                    "filingDate": ["2024-03-15", "2024-02-15", "2024-01-15", "2023-12-15"],
                    "accessionNumber": ["0000862084-24-000012", "0000862084-24-000011", 
                                      "0000862084-24-000010", "0000862084-23-000089"],
                    "primaryDocument": ["vusxx_497k.htm", "annual_report.htm", 
                                      "vusxx_497.htm", "registration.htm"]
                }
            }
        }
        mock_get.return_value = mock_response
        
        # Execute
        result = self.client._search_filings_via_submissions(self.sample_cik)
        
        # Verify
        self.assertIsNotNone(result)
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)
        
        # Check that only prospectus forms are included
        for filing in result:
            self.assertIn(filing['form'], ['497K', '497', 'N-1A'])

    def test_find_latest_prospectus_prioritization(self):
        """Test prospectus prioritization logic"""
        # Setup test filings
        filings = [
            {'form': '497', 'filingDate': '2024-03-15'},
            {'form': '497K', 'filingDate': '2024-03-10'},
            {'form': 'N-1A', 'filingDate': '2024-03-20'},
        ]
        
        # Execute
        result = self.client._find_latest_prospectus(filings)
        
        # Verify - should prioritize 497K over others
        self.assertIsNotNone(result)
        self.assertEqual(result['form'], '497K')

    def test_find_latest_prospectus_empty_list(self):
        """Test prospectus finding with empty filing list"""
        result = self.client._find_latest_prospectus([])
        self.assertIsNone(result)

    @patch('requests.Session.get')
    def test_download_document_success(self, mock_get):
        """Test successful document download"""
        # Setup
        sample_content = b"<html>Sample prospectus content</html>"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = sample_content
        mock_get.return_value = mock_response
        
        # Execute
        result = self.client._download_document("https://www.sec.gov/sample.htm")
        
        # Verify
        self.assertEqual(result, sample_content)

    @patch('requests.Session.get')
    def test_download_document_failure(self, mock_get):
        """Test document download failure"""
        # Setup
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        # Execute
        result = self.client._download_document("https://www.sec.gov/nonexistent.htm")
        
        # Verify
        self.assertIsNone(result)

    def test_build_document_url(self):
        """Test document URL building"""
        cik = "0000862084"
        accession = "0000862084-24-000012"
        document = "vusxx_497k.htm"
        
        result = self.client._build_document_url(cik, accession, document)
        
        expected = "https://www.sec.gov/Archives/edgar/data/862084/000086208424000012/vusxx_497k.htm"
        self.assertEqual(result, expected)

    def test_determine_document_type(self):
        """Test document type determination"""
        # Test PDF
        pdf_result = self.client._determine_document_type("https://example.com/doc.pdf")
        self.assertEqual(pdf_result, "PDF")
        
        # Test HTML
        html_result = self.client._determine_document_type("https://example.com/doc.htm")
        self.assertEqual(html_result, "HTML")
        
        # Test default
        default_result = self.client._determine_document_type("https://example.com/doc.unknown")
        self.assertEqual(default_result, "HTML")

    @patch('time.sleep')
    def test_rate_limit(self, mock_sleep):
        """Test rate limiting functionality"""
        self.client._rate_limit()
        mock_sleep.assert_called_once()

    @patch('src.sec_client.SECClient._find_cik_by_symbol')
    def test_get_latest_prospectus_exception_handling(self, mock_find_cik):
        """Test exception handling in get_latest_prospectus"""
        # Setup
        mock_find_cik.side_effect = Exception("Network error")
        
        # Execute
        result = self.client.get_latest_prospectus(self.sample_fund_symbol)
        
        # Verify
        self.assertIsNone(result)

    @patch('requests.Session.get')
    def test_search_edgar_filings_exception_handling(self, mock_get):
        """Test exception handling in search_edgar_filings"""
        # Setup
        mock_get.side_effect = Exception("Network error")
        
        # Execute
        result = self.client._search_edgar_filings(self.sample_cik, self.sample_fund_symbol)
        
        # Verify
        self.assertIsNone(result)

    def test_search_filings_via_submissions_invalid_response(self):
        """Test submissions API with invalid response format"""
        with patch('requests.Session.get') as mock_get:
            # Setup invalid response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"invalid": "structure"}
            mock_get.return_value = mock_response
            
            # Execute
            result = self.client._search_filings_via_submissions(self.sample_cik)
            
            # Verify
            self.assertIsNone(result)

    def test_multiple_fund_symbols(self):
        """Test that client can handle different fund symbol formats"""
        test_symbols = ["VUSXX", "SPY", "QQQ", "VTSAX", "FXNAX"]
        
        for symbol in test_symbols:
            # This should not raise exceptions
            with patch.object(self.client, '_find_cik_by_symbol', return_value=None):
                result = self.client.get_latest_prospectus(symbol)
                self.assertIsNone(result)  # Expected since we're mocking no CIK found

    def _create_sample_filing(self):
        """Helper method to create sample filing data"""
        return {
            'form': '497K',
            'filingDate': '2024-03-15',
            'accessionNumber': '0000862084-24-000012',
            'primaryDocument': 'vusxx_497k.htm',
            'documentUrl': 'https://www.sec.gov/Archives/edgar/data/862084/000086208424000012/vusxx_497k.htm'
        }


class TestSECClientIntegration(unittest.TestCase):
    """Integration tests that test multiple components together"""
    
    def setUp(self):
        self.client = SECClient()
    
    @patch('requests.Session.get')
    def test_full_workflow_mock(self, mock_get):
        """Test the complete workflow with mocked responses"""
        
        def mock_get_side_effect(url):
            mock_response = Mock()
            
            if 'company_tickers_mf.json' in url:
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "0": {
                        "ticker": "VUSXX",
                        "cik_str": 862084,
                        "title": "Vanguard Federal Money Market Fund"
                    }
                }
            elif 'submissions' in url:
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "filings": {
                        "recent": {
                            "form": ["497K"],
                            "filingDate": ["2024-03-15"],
                            "accessionNumber": ["0000862084-24-000012"],
                            "primaryDocument": ["vusxx_497k.htm"]
                        }
                    }
                }
            elif 'edgar/data' in url:
                mock_response.status_code = 200
                mock_response.content = b"<html>Sample prospectus content</html>"
            else:
                mock_response.status_code = 404
            
            return mock_response
        
        mock_get.side_effect = mock_get_side_effect
        
        # Execute
        result = self.client.get_latest_prospectus("VUSXX")
        
        # Verify
        self.assertIsNotNone(result)
        self.assertEqual(result.fund_symbol, "VUSXX")
        self.assertEqual(result.document_type, "HTML")


if __name__ == '__main__':
    # Configure test runner
    unittest.main(verbosity=2)