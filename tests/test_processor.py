"""
Unit tests for generic fund processor (Checkpoint 3).
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from src.generic_fund_processor import GenericFundProcessor, FundInfo, RetrievalResult
from src.models import ProspectusData


class TestGenericFundProcessor(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.processor = GenericFundProcessor()
        
    def test_initialization(self):
        """Test GenericFundProcessor initialization"""
        self.assertIsNotNone(self.processor.logger)
        self.assertIsNotNone(self.processor.sec_client)
        self.assertIsNotNone(self.processor.file_handler)
        self.assertIsNotNone(self.processor.session)
        self.assertIsNone(self.processor._tickers_cache)
        self.assertIsNone(self.processor._etf_cache)

    def test_detect_etf_provider_by_pattern(self):
        """Test ETF provider detection by ticker patterns"""
        # SPDR patterns
        self.assertEqual(self.processor._detect_etf_provider_by_pattern('SPY'), 'SPDR')
        self.assertEqual(self.processor._detect_etf_provider_by_pattern('XLF'), 'SPDR')
        self.assertEqual(self.processor._detect_etf_provider_by_pattern('GLD'), 'SPDR')
        
        # iShares patterns
        self.assertEqual(self.processor._detect_etf_provider_by_pattern('IWM'), 'iShares')
        self.assertEqual(self.processor._detect_etf_provider_by_pattern('EFA'), 'iShares')
        
        # Vanguard patterns
        self.assertEqual(self.processor._detect_etf_provider_by_pattern('VTI'), 'Vanguard')
        self.assertEqual(self.processor._detect_etf_provider_by_pattern('VOO'), 'Vanguard')
        
        # Invesco patterns
        self.assertEqual(self.processor._detect_etf_provider_by_pattern('QQQ'), 'Invesco')
        self.assertEqual(self.processor._detect_etf_provider_by_pattern('QQQM'), 'Invesco')
        
        # Unknown patterns
        self.assertIsNone(self.processor._detect_etf_provider_by_pattern('AAPL'))
        self.assertIsNone(self.processor._detect_etf_provider_by_pattern('UNKNOWN'))

    def test_get_provider_cik(self):
        """Test provider CIK lookup"""
        # Known providers
        self.assertEqual(self.processor._get_provider_cik('Vanguard'), '0000862084')
        self.assertEqual(self.processor._get_provider_cik('SPDR'), '0000884394')
        self.assertEqual(self.processor._get_provider_cik('iShares'), '0000930667')
        self.assertEqual(self.processor._get_provider_cik('Invesco'), '0000931748')
        self.assertEqual(self.processor._get_provider_cik('Fidelity'), '0000315066')
        
        # Unknown provider
        self.assertIsNone(self.processor._get_provider_cik('UnknownProvider'))

    def test_determine_provider_from_cik(self):
        """Test provider determination from CIK"""
        # Known CIKs
        self.assertEqual(self.processor._determine_provider_from_cik('0000862084'), 'Vanguard')
        self.assertEqual(self.processor._determine_provider_from_cik('0000884394'), 'SPDR')
        self.assertEqual(self.processor._determine_provider_from_cik('0000930667'), 'iShares')
        self.assertEqual(self.processor._determine_provider_from_cik('0000931748'), 'Invesco')
        
        # Unknown CIK
        self.assertIsNone(self.processor._determine_provider_from_cik('0000000000'))

    def test_discover_from_etf_sources_known_etfs(self):
        """Test ETF discovery for known ETFs"""
        # Test SPY
        result = self.processor._discover_from_etf_sources('SPY')
        self.assertIsNotNone(result)
        self.assertEqual(result.ticker, 'SPY')
        self.assertEqual(result.provider, 'SPDR')
        self.assertEqual(result.cik_str, '0000884394')
        self.assertEqual(result.fund_type, 'ETF')
        
        # Test QQQ
        result = self.processor._discover_from_etf_sources('QQQ')
        self.assertIsNotNone(result)
        self.assertEqual(result.ticker, 'QQQ')
        self.assertEqual(result.provider, 'Invesco')
        self.assertEqual(result.cik_str, '0000931748')
        
        # Test VTI
        result = self.processor._discover_from_etf_sources('VTI')
        self.assertIsNotNone(result)
        self.assertEqual(result.provider, 'Vanguard')
        self.assertEqual(result.cik_str, '0000862084')

    def test_discover_from_etf_sources_pattern_based(self):
        """Test ETF discovery using pattern-based detection"""
        # Test unknown Vanguard ETF
        result = self.processor._discover_from_etf_sources('VXX')
        self.assertIsNotNone(result)
        self.assertEqual(result.provider, 'Vanguard')
        self.assertEqual(result.fund_type, 'ETF')
        
        # Test unknown fund
        result = self.processor._discover_from_etf_sources('UNKNOWN')
        self.assertIsNone(result)

    @patch('requests.Session.get')
    def test_discover_from_mutual_fund_json(self, mock_get):
        """Test mutual fund discovery from SEC JSON"""
        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "fields": ["cik", "seriesId", "classId", "symbol"],
            "data": [
                [862084, "S000002811", "C000007474", "VUSXX"],
                [315066, "S000001234", "C000001234", "FXAIX"]
            ]
        }
        mock_get.return_value = mock_response
        
        # Test VUSXX discovery
        result = self.processor._discover_from_mutual_fund_json('VUSXX')
        self.assertIsNotNone(result)
        self.assertEqual(result.ticker, 'VUSXX')
        self.assertEqual(result.cik_str, '0000862084')
        self.assertEqual(result.provider, 'Vanguard')
        
        # Test unknown fund
        result = self.processor._discover_from_mutual_fund_json('UNKNOWN')
        self.assertIsNone(result)

    @patch('requests.Session.get')
    def test_discover_by_direct_cik(self, mock_get):
        """Test direct CIK discovery"""
        # Setup mock response for valid CIK
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "entityName": "Vanguard Group Inc"
        }
        mock_get.return_value = mock_response
        
        # Test valid numeric CIK
        result = self.processor._discover_by_direct_cik('862084')
        self.assertIsNotNone(result)
        self.assertEqual(result.cik_str, '0000862084')
        self.assertEqual(result.title, 'Vanguard Group Inc')
        
        # Test non-numeric symbol
        result = self.processor._discover_by_direct_cik('SPY')
        self.assertIsNone(result)
        
        # Test invalid CIK
        mock_response.status_code = 404
        result = self.processor._discover_by_direct_cik('999999')
        self.assertIsNone(result)

    def test_discover_by_pattern_matching(self):
        """Test pattern-based fund discovery"""
        # Test Vanguard mutual fund pattern
        result = self.processor._discover_by_pattern_matching('VTSAX')
        self.assertIsNotNone(result)
        self.assertEqual(result.provider, 'Vanguard')
        self.assertEqual(result.fund_type, 'MUTUAL_FUND')
        
        # Test Vanguard ETF pattern
        result = self.processor._discover_by_pattern_matching('VTI')
        self.assertIsNotNone(result)
        self.assertEqual(result.provider, 'Vanguard')
        self.assertEqual(result.fund_type, 'ETF')
        
        # Test Fidelity pattern
        result = self.processor._discover_by_pattern_matching('FXAIX')
        self.assertIsNotNone(result)
        self.assertEqual(result.provider, 'Fidelity')
        self.assertEqual(result.fund_type, 'MUTUAL_FUND')
        
        # Test unknown pattern
        result = self.processor._discover_by_pattern_matching('UNKNOWN')
        self.assertIsNone(result)

    @patch('src.generic_fund_processor.GenericFundProcessor._discover_fund_info')
    @patch('src.generic_fund_processor.GenericFundProcessor.sec_client')
    @patch('src.generic_fund_processor.GenericFundProcessor.file_handler')
    def test_retrieve_fund_prospectus_success(self, mock_file_handler, mock_sec_client, mock_discover):
        """Test successful fund prospectus retrieval"""
        # Setup mocks
        test_fund_info = FundInfo(
            ticker='SPY',
            cik_str='0000884394',
            title='SPDR S&P 500 ETF',
            provider='SPDR',
            fund_type='ETF'
        )
        mock_discover.return_value = test_fund_info
        
        test_prospectus = Mock()
        test_prospectus.content = b"Test prospectus content"
        test_prospectus.filing_date = datetime(2024, 3, 15)
        test_prospectus.form_type = "497"
        mock_sec_client.get_latest_prospectus.return_value = test_prospectus
        
        mock_file_handler.save_prospectus.return_value = "/test/path/SPY_497_20240315.html"
        
        # Execute
        result = self.processor.retrieve_fund_prospectus('SPY')
        
        # Verify
        self.assertTrue(result.success)
        self.assertEqual(result.fund.ticker, 'SPY')
        self.assertEqual(result.fund.provider, 'SPDR')
        self.assertEqual(result.fund.fund_type, 'ETF')
        self.assertIsNotNone(result.file_path)
        self.assertEqual(result.file_size, len(test_prospectus.content))

    @patch('src.generic_fund_processor.GenericFundProcessor._discover_fund_info')
    def test_retrieve_fund_prospectus_discovery_failed(self, mock_discover):
        """Test fund prospectus retrieval when discovery fails"""
        # Setup mock to return None (discovery failed)
        mock_discover.return_value = None
        
        # Execute
        result = self.processor.retrieve_fund_prospectus('UNKNOWN')
        
        # Verify
        self.assertFalse(result.success)
        self.assertEqual(result.error_category, 'DISCOVERY_FAILED')
        self.assertIn('Could not discover fund information', result.error_message)

    def test_retrieve_fund_prospectus_invalid_symbol(self):
        """Test fund prospectus retrieval with invalid symbol"""
        # Execute
        result = self.processor.retrieve_fund_prospectus('INVALID!')
        
        # Verify
        self.assertFalse(result.success)
        self.assertEqual(result.error_category, 'INVALID_SYMBOL')
        self.assertIn('Invalid fund symbol format', result.error_message)

    @patch('src.generic_fund_processor.GenericFundProcessor.retrieve_fund_prospectus')
    def test_process_multiple_funds(self, mock_retrieve):
        """Test multiple fund processing"""
        # Setup mock results
        mock_results = [
            RetrievalResult(
                fund=FundInfo(ticker='SPY'),
                success=True,
                file_size=100000,
                discovery_method='SPDR'
            ),
            RetrievalResult(
                fund=FundInfo(ticker='QQQ'),
                success=True,
                file_size=150000,
                discovery_method='Invesco'
            ),
            RetrievalResult(
                fund=FundInfo(ticker='UNKNOWN'),
                success=False,
                error_message='Discovery failed',
                error_category='DISCOVERY_FAILED'
            )
        ]
        mock_retrieve.side_effect = mock_results
        
        with patch.object(self.processor, '_log_batch_summary'):
            with patch.object(self.processor, '_save_batch_results'):
                # Execute
                results = self.processor.process_multiple_funds(['SPY', 'QQQ', 'UNKNOWN'], skip_existing=False)
        
        # Verify
        self.assertEqual(len(results), 3)
        self.assertEqual(sum(1 for r in results if r.success), 2)
        self.assertEqual(sum(1 for r in results if not r.success), 1)

    def test_format_file_size(self):
        """Test file size formatting"""
        self.assertEqual(self.processor._format_file_size(1024), "1.0 KB")
        self.assertEqual(self.processor._format_file_size(1048576), "1.0 MB")
        self.assertEqual(self.processor._format_file_size(500), "500.0 B")


class TestFundDataStructures(unittest.TestCase):
    """Test the data structures used in generic fund processing"""
    
    def test_fund_info_creation(self):
        """Test FundInfo data structure"""
        fund = FundInfo(
            ticker="SPY",
            cik_str="0000884394",
            title="SPDR S&P 500 ETF",
            fund_type="ETF",
            provider="SPDR"
        )
        
        self.assertEqual(fund.ticker, "SPY")
        self.assertEqual(fund.cik_str, "0000884394")
        self.assertEqual(fund.title, "SPDR S&P 500 ETF")
        self.assertEqual(fund.fund_type, "ETF")
        self.assertEqual(fund.provider, "SPDR")

    def test_retrieval_result_creation(self):
        """Test RetrievalResult data structure"""
        fund = FundInfo("SPY", "0000884394", "SPDR S&P 500 ETF", "ETF", "SPDR")
        filing_date = datetime.now()
        
        result = RetrievalResult(
            fund=fund,
            success=True,
            file_path="/test/path.html",
            file_size=100000,
            filing_date=filing_date,
            form_type="497",
            discovery_method="SPDR",
            processing_time=1.5
        )
        
        self.assertEqual(result.fund, fund)
        self.assertTrue(result.success)
        self.assertEqual(result.file_path, "/test/path.html")
        self.assertEqual(result.file_size, 100000)
        self.assertEqual(result.form_type, "497")
        self.assertEqual(result.discovery_method, "SPDR")
        self.assertEqual(result.processing_time, 1.5)


class TestDiscoveryStrategies(unittest.TestCase):
    """Test various fund discovery strategies"""
    
    def setUp(self):
        self.processor = GenericFundProcessor()
    
    @patch('src.generic_fund_processor.GenericFundProcessor._discover_from_mutual_fund_json')
    @patch('src.generic_fund_processor.GenericFundProcessor._discover_from_etf_sources')
    @patch('src.generic_fund_processor.GenericFundProcessor._discover_by_direct_cik')
    @patch('src.generic_fund_processor.GenericFundProcessor._discover_by_pattern_matching')
    def test_discover_fund_info_strategy_priority(self, mock_pattern, mock_cik, mock_etf, mock_mf):
        """Test that discovery strategies are tried in correct priority order"""
        # Setup mocks to return None initially
        mock_mf.return_value = None
        mock_etf.return_value = None
        mock_cik.return_value = None
        mock_pattern.return_value = FundInfo("TEST", "0000000000", "Test Fund")
        
        # Execute
        result = self.processor._discover_fund_info("TEST")
        
        # Verify all strategies were called in order
        mock_mf.assert_called_once_with("TEST")
        mock_etf.assert_called_once_with("TEST")
        mock_cik.assert_called_once_with("TEST")
        mock_pattern.assert_called_once_with("TEST")
        self.assertIsNotNone(result)
    
    def test_discover_fund_info_early_return(self):
        """Test that discovery stops at first successful strategy"""
        with patch.object(self.processor, '_discover_from_mutual_fund_json') as mock_mf:
            with patch.object(self.processor, '_discover_from_etf_sources') as mock_etf:
                # Setup first strategy to succeed
                mock_mf.return_value = FundInfo("TEST", "0000000000", "Test Fund", "MUTUAL_FUND")
                
                # Execute
                result = self.processor._discover_fund_info("TEST")
                
                # Verify only first strategy was called
                mock_mf.assert_called_once_with("TEST")
                mock_etf.assert_not_called()
                self.assertIsNotNone(result)
                self.assertEqual(result.fund_type, "MUTUAL_FUND")


class TestArbitraryFundIntegration(unittest.TestCase):
    """Integration tests for arbitrary fund processing"""
    
    def setUp(self):
        self.processor = GenericFundProcessor()
    
    @patch('requests.Session.get')
    @patch('src.generic_fund_processor.GenericFundProcessor.sec_client')
    @patch('src.generic_fund_processor.GenericFundProcessor.file_handler')
    def test_end_to_end_etf_processing(self, mock_file_handler, mock_sec_client, mock_get):
        """Test complete ETF processing workflow"""
        # Setup mocks
        test_prospectus = Mock()
        test_prospectus.content = b"Test ETF prospectus content"
        test_prospectus.filing_date = datetime(2024, 3, 15)
        test_prospectus.form_type = "497"
        mock_sec_client.get_latest_prospectus.return_value = test_prospectus
        
        mock_file_handler.save_prospectus.return_value = "/test/SPY_497_20240315.html"
        
        # Execute
        result = self.processor.retrieve_fund_prospectus("SPY")
        
        # Verify
        self.assertTrue(result.success)
        self.assertEqual(result.fund.ticker, "SPY")
        self.assertEqual(result.fund.provider, "SPDR")
        self.assertEqual(result.fund.fund_type, "ETF")
    
    def test_multiple_fund_types_handling(self):
        """Test handling of different fund types"""
        test_symbols = ["SPY", "QQQ", "VTSAX", "FXAIX"]
        
        for symbol in test_symbols:
            with patch.object(self.processor, '_discover_fund_info', return_value=None):
                # This should not raise exceptions
                result = self.processor.retrieve_fund_prospectus(symbol)
                self.assertFalse(result.success)  # Expected since we're mocking no discovery


if __name__ == '__main__':
    unittest.main(verbosity=2)