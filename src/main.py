#!/usr/bin/env python3
"""
Main entry point for fund prospectus retrieval.
Checkpoint 1: Single fund retrieval for VUSXX.
"""

import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings
from src.sec_client import SECClient
from src.file_handler import FileHandler
from src.utils import setup_logging, validate_fund_symbol, normalize_fund_symbol

def main():
    """Main function for checkpoint 1: retrieve VUSXX prospectus"""
    # Setup
    settings.ensure_directories()
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Retrieve fund prospectuses from SEC EDGAR')
    parser.add_argument('--symbol', '-s', default='VUSXX', 
                       help='Fund symbol to retrieve (default: VUSXX)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Validate and normalize fund symbol
    fund_symbol = normalize_fund_symbol(args.symbol)
    if not fund_symbol:
        logger.error(f"Invalid fund symbol: {args.symbol}")
        sys.exit(1)
    
    # Initialize components
    sec_client = SECClient()
    file_handler = FileHandler()
    
    try:
        logger.info(f"=== Starting prospectus retrieval for {fund_symbol} ===")
        start_time = datetime.now()
        
        # Check if we already have this prospectus
        existing_file = file_handler.get_existing_prospectus(fund_symbol)
        if existing_file:
            logger.info(f"Found existing prospectus: {existing_file}")
            metadata = file_handler.load_metadata(existing_file)
            if metadata:
                logger.info(f"Existing file date: {metadata.get('filing_date')}")
                logger.info("Use --force flag to re-download")
        
        # Retrieve prospectus
        logger.info(f"Searching SEC EDGAR for {fund_symbol} prospectus...")
        prospectus_data = sec_client.get_latest_prospectus(fund_symbol)
        
        if prospectus_data:
            # Save to local storage
            logger.info("Saving prospectus to local storage...")
            saved_path = file_handler.save_prospectus(prospectus_data)
            
            # Log success information
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            logger.info("=== SUCCESS ===")
            logger.info(f"Fund Symbol: {prospectus_data.fund_symbol}")
            logger.info(f"Filing Date: {prospectus_data.filing_date.strftime('%Y-%m-%d')}")
            logger.info(f"Form Type: {prospectus_data.form_type}")
            logger.info(f"Document Type: {prospectus_data.document_type}")
            logger.info(f"File Size: {len(prospectus_data.content):,} bytes")
            logger.info(f"Saved to: {saved_path}")
            logger.info(f"Source URL: {prospectus_data.source_url}")
            logger.info(f"CIK: {prospectus_data.cik}")
            logger.info(f"Accession Number: {prospectus_data.accession_number}")
            logger.info(f"Total time: {duration:.2f} seconds")
            
            print(f"\n Successfully retrieved and saved prospectus for {fund_symbol}")
            print(f" Saved to: {saved_path}")
            print(f" File size: {len(prospectus_data.content):,} bytes")
            print(f" Filing date: {prospectus_data.filing_date.strftime('%Y-%m-%d')}")
            
        else:
            logger.error(f"Failed to retrieve prospectus for {fund_symbol}")
            print(f"\n Failed to retrieve prospectus for {fund_symbol}")
            print("Check the logs for more details.")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        print("\n Operation cancelled")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        print(f"\n Error: {str(e)}")
        print("Check the logs for more details.")
        sys.exit(1)

if __name__ == "__main__":
    main()