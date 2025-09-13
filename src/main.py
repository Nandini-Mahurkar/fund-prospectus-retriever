#!/usr/bin/env python3
"""
Main entry point for fund prospectus retrieval.
Checkpoint 1: Single fund retrieval for VUSXX.
Checkpoint 2: Multiple Vanguard funds batch processing.
Checkpoint 3: Arbitrary fund retrieval (any fund symbol).
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
from src.generic_fund_processor import GenericFundProcessor
from src.utils import setup_logging, validate_fund_symbol, normalize_fund_symbol

def main():
    """Main function supporting single fund, batch Vanguard, and arbitrary fund processing"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Retrieve fund prospectuses from SEC EDGAR',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Checkpoint 1: Single fund
  python src/main.py --symbol VUSXX
  
  # Checkpoint 2: All Vanguard funds
  python src/main.py --batch-vanguard
  
  # Checkpoint 3: Single arbitrary fund
  python src/main.py --arbitrary SPY
  python src/main.py --arbitrary QQQ
  
  # Checkpoint 3: Multiple arbitrary funds
  python src/main.py --arbitrary-batch SPY QQQ IWM VTI
  
  # Mixed processing
  python src/main.py --arbitrary-batch SPY QQQ --max-funds 10
        """
    )
    
    # Mode selection
    mode_group = parser.add_mutually_exclusive_group(required=False)
    mode_group.add_argument('--symbol', '-s', 
                           help='Single fund symbol to retrieve (Checkpoint 1)')
    mode_group.add_argument('--batch-vanguard', action='store_true',
                           help='Process all Vanguard mutual funds (Checkpoint 2)')
    mode_group.add_argument('--arbitrary', 
                           help='Single arbitrary fund symbol (Checkpoint 3)')
    mode_group.add_argument('--arbitrary-batch', nargs='+', metavar='SYMBOL',
                           help='Multiple arbitrary fund symbols (Checkpoint 3)')
    
    # Batch processing options
    parser.add_argument('--max-funds', type=int, 
                       help='Maximum number of funds to process (for testing)')
    parser.add_argument('--skip-existing', action='store_true', default=True,
                       help='Skip funds that already have downloaded prospectuses')
    parser.add_argument('--force', action='store_true',
                       help='Re-download even if prospectus already exists')
    
    # General options
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without actually downloading')
    
    args = parser.parse_args()
    
    # Default to VUSXX if no mode specified
    if not any([args.symbol, args.batch_vanguard, args.arbitrary, args.arbitrary_batch]):
        args.symbol = 'VUSXX'
    
    # Setup
    settings.ensure_directories()
    setup_logging()
    logger = logging.getLogger(__name__)
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Handle force flag
    if args.force:
        args.skip_existing = False
    
    try:
        if args.batch_vanguard:
            # Checkpoint 2: Batch processing mode
            run_batch_processing(args, logger)
        elif args.arbitrary:
            # Checkpoint 3: Single arbitrary fund
            run_arbitrary_fund_processing(args, logger, [args.arbitrary])
        elif args.arbitrary_batch:
            # Checkpoint 3: Multiple arbitrary funds
            run_arbitrary_fund_processing(args, logger, args.arbitrary_batch)
        else:
            # Checkpoint 1: Single fund mode
            run_single_fund_processing(args, logger)
            
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        print("\nOperation cancelled")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        print(f"\nError: {str(e)}")
        print("Check the logs for more details.")
        sys.exit(1)

def run_single_fund_processing(args, logger):
    """Run single fund processing (Checkpoint 1)"""
    # Validate and normalize fund symbol
    fund_symbol = normalize_fund_symbol(args.symbol)
    if not fund_symbol:
        logger.error(f"Invalid fund symbol: {args.symbol}")
        sys.exit(1)
    
    # Initialize components
    sec_client = SECClient()
    file_handler = FileHandler()
    
    logger.info(f"=== Starting prospectus retrieval for {fund_symbol} ===")
    start_time = datetime.now()
    
    # Check if we already have this prospectus
    if args.skip_existing:
        existing_file = file_handler.get_existing_prospectus(fund_symbol)
        if existing_file:
            logger.info(f"Found existing prospectus: {existing_file}")
            metadata = file_handler.load_metadata(existing_file)
            if metadata:
                logger.info(f"Existing file date: {metadata.get('filing_date')}")
                if not args.force:
                    print(f"Prospectus for {fund_symbol} already exists: {existing_file}")
                    print("Use --force to re-download")
                    return
    
    if args.dry_run:
        print(f"Would retrieve prospectus for: {fund_symbol}")
        return
    
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
        
        print(f"\nSuccessfully retrieved and saved prospectus for {fund_symbol}")
        print(f"Saved to: {saved_path}")
        print(f"File size: {len(prospectus_data.content):,} bytes")
        print(f"Filing date: {prospectus_data.filing_date.strftime('%Y-%m-%d')}")
        
    else:
        logger.error(f"Failed to retrieve prospectus for {fund_symbol}")
        print(f"\nFailed to retrieve prospectus for {fund_symbol}")
        print("Check the logs for more details.")
        sys.exit(1)

def run_batch_processing(args, logger):
    """Run batch processing for all Vanguard funds (Checkpoint 2)"""
    logger.info("=== Starting Vanguard batch processing (Checkpoint 2) ===")
    
    # Initialize batch processor
    processor = VanguardFundProcessor()
    
    try:
        if args.dry_run:
            # Dry run: just show what funds would be processed
            vanguard_funds = processor.get_vanguard_funds()
            if args.max_funds:
                vanguard_funds = vanguard_funds[:args.max_funds]
            
            print(f"\nDRY RUN: Would process {len(vanguard_funds)} Vanguard funds:")
            for i, fund in enumerate(vanguard_funds[:20], 1):  # Show first 20
                print(f"  {i:3d}. {fund.ticker:6s} - {fund.title}")
            if len(vanguard_funds) > 20:
                print(f"  ... and {len(vanguard_funds) - 20} more funds")
            print(f"\nUse --max-funds to limit for testing")
            return
        
        # Run actual batch processing
        start_time = datetime.now()
        results = processor.process_all_funds(
            max_funds=args.max_funds,
            skip_existing=args.skip_existing
        )
        
        # Generate and display final summary
        end_time = datetime.now()
        total_duration = (end_time - start_time).total_seconds()
        
        successful = [r for r in results if r.success and not (r.error_message and "already exists" in r.error_message)]
        failed = [r for r in results if not r.success]
        skipped = [r for r in results if r.success and r.error_message and "already exists" in r.error_message]
        
        print(f"\nBATCH PROCESSING COMPLETED")
        print(f"Total time: {total_duration:.1f} seconds")
        print(f"Results:")
        print(f"Successfully downloaded: {len(successful)} funds")
        print(f"Skipped (already exist): {len(skipped)} funds")
        print(f"Failed: {len(failed)} funds")
        print(f"Success rate: {(len(successful) / len(results) * 100):.1f}%")
        
        if successful:
            total_size = sum(r.file_size or 0 for r in successful)
            print(f"Total data downloaded: {processor._format_file_size(total_size)}")
        
        print(f"\nDetailed results saved to: data/prospectuses/vanguard_batch_results.json")
        print(f"Prospectuses saved in: data/prospectuses/[TICKER]/")
        
        if failed and len(failed) <= 10:
            print(f"\nFailed funds:")
            for result in failed:
                print(f"   • {result.fund.ticker}: {result.error_message}")
        elif failed:
            print(f"\n{len(failed)} funds failed - see detailed logs for more information")
        
    except Exception as e:
        logger.error(f"Batch processing failed: {str(e)}", exc_info=True)
        print(f"\nBatch processing failed: {str(e)}")
        print("Check the logs for more details.")
        sys.exit(1)

def run_arbitrary_fund_processing(args, logger, fund_symbols):
    """Run arbitrary fund processing (Checkpoint 3)"""
    logger.info(f"=== Starting arbitrary fund processing (Checkpoint 3) ===")
    
    # Initialize generic processor
    processor = GenericFundProcessor()
    
    try:
        if args.dry_run:
            print(f"\nDRY RUN: Would process {len(fund_symbols)} arbitrary fund(s):")
            for i, symbol in enumerate(fund_symbols, 1):
                print(f"  {i:3d}. {symbol}")
            print(f"\nFunds will be processed using multiple discovery strategies:")
            print(f"  1. SEC mutual fund tickers JSON")
            print(f"  2. Known ETF patterns and providers")
            print(f"  3. Direct CIK lookup")
            print(f"  4. SEC entity search")
            print(f"  5. Web-based lookup")
            print(f"  6. Expanded pattern matching")
            print(f"  7. Brute force search")
            print(f"  8. Generic fund creation (last resort)")
            return
        
        if len(fund_symbols) == 1:
            # Single fund processing
            symbol = fund_symbols[0]
            start_time = datetime.now()
            
            # Check existing file
            if args.skip_existing:
                existing_file = processor.file_handler.get_existing_prospectus(symbol)
                if existing_file:
                    print(f"Prospectus for {symbol} already exists: {existing_file}")
                    print("Use --force to re-download")
                    return
            
            result = processor.retrieve_fund_prospectus(symbol)
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            if result.success:
                print(f"\nSuccessfully retrieved prospectus for {symbol}")
                print(f"Provider: {result.fund.provider or 'Unknown'}")
                print(f"Fund Type: {result.fund.fund_type or 'Unknown'}")
                print(f"Discovery Method: {result.discovery_method or 'Unknown'}")
                print(f"Saved to: {result.file_path}")
                print(f"File size: {result.file_size:,} bytes")
                print(f"Form type: {result.form_type}")
                print(f"Filing date: {result.filing_date.strftime('%Y-%m-%d') if result.filing_date else 'Unknown'}")
                print(f"Processing time: {duration:.2f} seconds")
            else:
                print(f"\nFailed to retrieve prospectus for {symbol}")
                print(f"Error: {result.error_message}")
                print(f"Category: {result.error_category}")
                print("Check the logs for more details.")
                sys.exit(1)
        
        else:
            # Multiple funds batch processing
            if args.max_funds:
                fund_symbols = fund_symbols[:args.max_funds]
                logger.info(f"Limited to first {args.max_funds} funds for testing")
            
            start_time = datetime.now()
            results = processor.process_multiple_funds(fund_symbols, args.skip_existing)
            
            end_time = datetime.now()
            total_duration = (end_time - start_time).total_seconds()
            
            # Generate summary
            successful = [r for r in results if r.success and not (r.error_message and "already exists" in r.error_message)]
            failed = [r for r in results if not r.success]
            skipped = [r for r in results if r.success and r.error_message and "already exists" in r.error_message]
            
            print(f"\nARBITRARY FUND BATCH PROCESSING COMPLETED")
            print(f"Total time: {total_duration:.1f} seconds")
            print(f"Results:")
            print(f"Successfully downloaded: {len(successful)} funds")
            print(f"Skipped (already exist): {len(skipped)} funds")
            print(f"Failed: {len(failed)} funds")
            print(f"Success rate: {(len(successful) / len(results) * 100):.1f}%")
            
            if successful:
                total_size = sum(r.file_size or 0 for r in successful)
                print(f"Total data downloaded: {processor._format_file_size(total_size)}")
            
            # Show discovery method breakdown
            discovery_methods = {}
            for result in successful:
                method = result.discovery_method or "Unknown"
                discovery_methods[method] = discovery_methods.get(method, 0) + 1
            
            if discovery_methods:
                print(f"\nDiscovery methods used:")
                for method, count in discovery_methods.items():
                    print(f"  {method}: {count} funds")
            
            print(f"\nDetailed results saved to: data/prospectuses/arbitrary_batch_results.json")
            print(f"Prospectuses saved in: data/prospectuses/[TICKER]/")
            
            if failed and len(failed) <= 10:
                print(f"\nFailed funds:")
                for result in failed:
                    print(f"   • {result.fund.ticker}: {result.error_message} ({result.error_category})")
            elif failed:
                print(f"\n{len(failed)} funds failed - see detailed logs for more information")
        
    except Exception as e:
        logger.error(f"Arbitrary fund processing failed: {str(e)}", exc_info=True)
        print(f"\nArbitrary fund processing failed: {str(e)}")
        print("Check the logs for more details.")
        sys.exit(1)

if __name__ == "__main__":
    main()