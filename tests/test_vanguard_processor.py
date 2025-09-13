"""
Unit tests for Vanguard batch processing functionality.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import json

from src.vanguard_processor import VanguardFundProcessor, VanguardFund, ProcessingResult
from src.models import ProspectusData


class TestVanguardFundProcessor(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.processor = VanguardFundProcessor()
        
    def test_initialization(self):
        """Test VanguardFundProcessor initialization"""
        self.assertIsNotNone(self.processor.logger)
        self.assertIsNotNone(self.processor.sec_client)
        self.assertIsNotNone(self.processor.file_handler)
        self.assertIsNotNone(self.processor.session)
        
    def test_is_vanguard_fund_by_title(self):
        """Test Vanguard fund identification by title"""
        # Positive cases
        self.assertTrue(self.processor._is_vanguard_fund("VANGUARD FEDERAL MONEY MARKET FUND", "VUSXX"))
        self.assertTrue(self.processor._is_vanguard_fund("VG INTERNATIONAL EQUITY FUND", "VTISX"))
        self.assertTrue(self.processor._is_vanguard_fund("ADMIRAL SHARES TOTAL STOCK MARKET", "VTSAX"))
        
        # Negative cases
        self.assertFalse(self.processor._is_vanguard_fund("FIDELITY TOTAL MARKET INDEX", "FXAIX"))
        self.assertFalse(self.processor._is_vanguard_fund("SPDR S&P 500 ETF", "SPY"))
        
    def test_is_vanguard_fund_by_ticker(self):
        """Test Vanguard fund identification by ticker pattern"""
        # Positive cases - Vanguard ticker patterns
        self.assertTrue(self.processor._is_vanguard_fund("Some Fund", "VUSXX"))
        self.assertTrue(self.processor._is_vanguard_fund("Another Fund", "VTSAX"))
        self.assertTrue(self.processor._is_vanguard_fund("Fund Name", "VTIAX"))
        
        # Negative cases - Non-Vanguard patterns
        self.assertFalse(self.processor._is_vanguard_fund("Fund Name", "FXAIX"))
        self.assertFalse(self.processor._is_vanguard_fund("Fund Name", "SPY"))
        self.assertFalse(self.processor._is_vanguard_fund("Fund Name", "QQQ"))
        
    @patch('requests.Session.get')
    def test_get_vanguard_funds_success(self, mock_get):
        """Test successful retrieval of Vanguard funds"""
        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "0": {
                "ticker": "VUSXX",
                "cik_str": 862084,
                "title": "Vanguard Federal Money Market Fund",
                "series_id": "S000002811",
                "class_id": "C000007474"
            },
            "1": {
                "ticker": "VTSAX",
                "cik_str": 862084,
                "title": "Vanguard Total Stock Market Index Fund Admiral Shares",
                "series_id": "S000002809",
                "class_id": "C000007471"
            },
            "2": {
                "ticker": "FXAIX",
                "cik_str": 315066,
                "title": "Fidelity 500 Index Fund",
                "series_id": "S000002810",
                "class_id": "C000007472"
            }
        }
        mock_get.return_value = mock_response
        
        # Execute
        vanguard_funds = self.processor.get_vanguard_funds()
        
        # Verify
        self.assertEqual(len(vanguard_funds), 2)  # Only VUSXX and VTSAX should be identified as Vanguard
        
        # Check first fund
        vusxx_fund = next(f for f in vanguard_funds if f.ticker == "VUSXX")
        self.assertEqual(vusxx_fund.ticker, "VUSXX")
        self.assertEqual(vusxx_fund.cik_str, "0000862084")
        self.assertEqual(vusxx_fund.series_id, "S000002811")
        
        # Check second fund
        vtsax_fund = next(f for f in vanguard_funds if f.ticker == "VTSAX")
        self.assertEqual(vtsax_fund.ticker, "VTSAX")
        self.assertEqual(vtsax_fund.title, "Vanguard Total Stock Market Index Fund Admiral Shares")
        
    @patch('requests.Session.get')
    def test_get_vanguard_funds_api_failure(self, mock_get):
        """Test handling of API failure when fetching Vanguard funds"""
        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        # Execute and verify exception
        with self.assertRaises(Exception) as context:
            self.processor.get_vanguard_funds()
        
        self.assertIn("Failed to fetch company tickers", str(context.exception))
        
    @patch('src.vanguard_processor.VanguardFundProcessor._process_single_fund')
    @patch('src.vanguard_processor.VanguardFundProcessor.get_vanguard_funds')
    def test_process_all_funds_success(self, mock_get_funds, mock_process_single):
        """Test successful batch processing of multiple funds"""
        # Setup test data
        test_funds = [
            VanguardFund("VUSXX", "0000862084", "Vanguard Federal Money Market Fund"),
            VanguardFund("VTSAX", "0000862084", "Vanguard Total Stock Market Index Fund")
        ]
        mock_get_funds.return_value = test_funds
        
        # Setup mock processing results
        mock_process_single.side_effect = [
            ProcessingResult(test_funds[0], True, "/path/to/vusxx.html", None, 100000, datetime.now(), "497K", 1.5),
            ProcessingResult(test_funds[1], True, "/path/to/vtsax.html", None, 150000, datetime.now(), "497", 2.0)
        ]
        
        # Execute
        results = self.processor.process_all_funds(max_funds=2)
        
        # Verify
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.success for r in results))
        self.assertEqual(mock_process_single.call_count, 2)
        
    def test_process_single_fund_skip_existing(self):
        """Test skipping existing fund during single fund processing"""
        # Setup
        test_fund = VanguardFund("VUSXX", "0000862084", "Vanguard Federal Money Market Fund")
        
        with patch.object(self.processor.file_handler, 'get_existing_prospectus') as mock_existing:
            mock_existing.return_value = Mock()  # Simulate existing file
            
            # Execute
            result = self.processor._process_single_fund(test_fund, skip_existing=True)
            
            # Verify
            self.assertTrue(result.success)
            self.assertIn("already exists", result.error_message)
            
    def test_process_single_fund_invalid_ticker(self):
        """Test handling of invalid ticker during single fund processing"""
        # Setup
        test_fund = VanguardFund("INVALID!", "0000862084", "Invalid Fund")
        
        # Execute
        result = self.processor._process_single_fund(test_fund, skip_existing=False)
        
        # Verify
        self.assertFalse(result.success)
        self.assertIn("Invalid ticker format", result.error_message)
        
    @patch('src.vanguard_processor.VanguardFundProcessor._save_batch_results')
    @patch('src.vanguard_processor.VanguardFundProcessor._log_batch_summary')
    def test_process_all_funds_with_max_limit(self, mock_log_summary, mock_save_results):
        """Test batch processing with maximum fund limit"""
        # Setup test data - more funds than the limit
        test_funds = [
            VanguardFund(f"VFU{i:02d}X", "0000862084", f"Vanguard Test Fund {i}")
            for i in range(20)
        ]
        
        with patch.object(self.processor, 'get_vanguard_funds', return_value=test_funds):
            with patch.object(self.processor, '_process_single_fund') as mock_process:
                mock_process.return_value = ProcessingResult(
                    test_funds[0], True, "/path/test.html", None, 100000, datetime.now(), "497K", 1.0
                )
                
                # Execute with limit
                results = self.processor.process_all_funds(max_funds=5)
                
                # Verify only 5 funds were processed
                self.assertEqual(len(results), 5)
                self.assertEqual(mock_process.call_count, 5)
                
    def test_categorize_error(self):
        """Test error categorization for analysis"""
        # Test different error categories
        self.assertEqual(self.processor._categorize_error("CIK not found"), "CIK_NOT_FOUND")
        self.assertEqual(self.processor._categorize_error("No prospectus filings found"), "NO_PROSPECTUS")
        self.assertEqual(self.processor._categorize_error("Network timeout occurred"), "NETWORK_ERROR")
        self.assertEqual(self.processor._categorize_error("Rate limit exceeded"), "RATE_LIMITED")
        self.assertEqual(self.processor._categorize_error("Invalid data format"), "INVALID_DATA")
        self.assertEqual(self.processor._categorize_error("Something unexpected"), "OTHER")
        
    def test_get_processing_statistics(self):
        """Test processing statistics generation"""
        # Setup test results
        test_fund1 = VanguardFund("VUSXX", "0000862084", "Fund 1")
        test_fund2 = VanguardFund("VTSAX", "0000862084", "Fund 2")
        test_fund3 = VanguardFund("VTIAX", "0000862084", "Fund 3")
        
        results = [
            ProcessingResult(test_fund1, True, "/path/1.html", None, 100000, datetime.now(), "497K", 1.0),
            ProcessingResult(test_fund2, False, None, "CIK not found", None, None, None, 0.5),
            ProcessingResult(test_fund3, True, "/path/3.html", "already exists", 150000, datetime.now(), "497", 1.5)
        ]
        
        # Execute
        stats = self.processor.get_processing_statistics(results)
        
        # Verify
        self.assertEqual(stats['total_funds'], 3)
        self.assertEqual(stats['successful_downloads'], 1)  # Only first one is new download
        self.assertEqual(stats['failed_downloads'], 1)
        self.assertEqual(stats['skipped_funds'], 1)
        self.assertAlmostEqual(stats['success_rate'], 33.33, places=1)
        self.assertEqual(stats['total_size_bytes'], 100000)
        self.assertIn('497K', stats['form_type_distribution'])
        self.assertIn('CIK_NOT_FOUND', stats['error_categories'])
        
    def test_format_file_size(self):
        """Test file size formatting"""
        self.assertEqual(self.processor._format_file_size(1024), "1.0 KB")
        self.assertEqual(self.processor._format_file_size(1048576), "1.0 MB")
        self.assertEqual(self.processor._format_file_size(1073741824), "1.0 GB")
        self.assertEqual(self.processor._format_file_size(500), "500.0 B")


class TestVanguardFundDataStructures(unittest.TestCase):
    """Test the data structures used in Vanguard processing"""
    
    def test_vanguard_fund_creation(self):
        """Test VanguardFund data structure"""
        fund = VanguardFund(
            ticker="VUSXX",
            cik_str="0000862084",
            title="Vanguard Federal Money Market Fund",
            series_id="S000002811",
            class_id="C000007474"
        )
        
        self.assertEqual(fund.ticker, "VUSXX")
        self.assertEqual(fund.cik_str, "0000862084")
        self.assertEqual(fund.title, "Vanguard Federal Money Market Fund")
        self.assertEqual(fund.series_id, "S000002811")
        self.assertEqual(fund.class_id, "C000007474")
        
    def test_processing_result_creation(self):
        """Test ProcessingResult data structure"""
        fund = VanguardFund("VUSXX", "0000862084", "Test Fund")
        filing_date = datetime.now()
        
        result = ProcessingResult(
            fund=fund,
            success=True,
            file_path="/path/to/file.html",
            error_message=None,
            file_size=100000,
            filing_date=filing_date,
            form_type="497K",
            processing_time=1.5
        )
        
        self.assertEqual(result.fund, fund)
        self.assertTrue(result.success)
        self.assertEqual(result.file_path, "/path/to/file.html")
        self.assertIsNone(result.error_message)
        self.assertEqual(result.file_size, 100000)
        self.assertEqual(result.filing_date, filing_date)
        self.assertEqual(result.form_type, "497K")
        self.assertEqual(result.processing_time, 1.5)


class TestVanguardFundProcessorIntegration(unittest.TestCase):
    """Integration tests for VanguardFundProcessor"""
    
    def setUp(self):
        self.processor = VanguardFundProcessor()
        
    @patch('requests.Session.get')
    @patch('src.vanguard_processor.VanguardFundProcessor._process_single_fund')
    def test_end_to_end_batch_processing(self, mock_process_single, mock_get):
        """Test complete end-to-end batch processing workflow"""
        # Setup mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "0": {
                "ticker": "VUSXX",
                "cik_str": 862084,
                "title": "Vanguard Federal Money Market Fund"
            }
        }
        mock_get.return_value = mock_response
        
        # Setup mock processing result
        test_fund = VanguardFund("VUSXX", "0000862084", "Vanguard Federal Money Market Fund")
        mock_process_single.return_value = ProcessingResult(
            fund=test_fund,
            success=True,
            file_path="/test/path.html",
            file_size=100000,
            filing_date=datetime.now(),
            form_type="497K",
            processing_time=1.0
        )
        
        # Execute
        with patch.object(self.processor, '_log_batch_summary'):
            with patch.object(self.processor, '_save_batch_results'):
                results = self.processor.process_all_funds(max_funds=1)
        
        # Verify
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].fund.ticker, "VUSXX")


if __name__ == '__main__':
    unittest.main(verbosity=2)