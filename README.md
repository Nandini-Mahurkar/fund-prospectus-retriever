# Fund Prospectus Retriever

A Python automation system that retrieves mutual fund prospectuses from the SEC EDGAR database. This implementation covers **Checkpoint 1** (single fund retrieval) and **Checkpoint 2** (batch Vanguard fund processing).

## Project Overview

This system accepts fund symbols and automatically retrieves the most recent prospectus filings from the SEC EDGAR API, saving them locally with comprehensive metadata tracking.

### Current Status: Checkpoint 2
- **Checkpoint 1**: Single fund retrieval (VUSXX)
- **Checkpoint 2**: Batch processing for all Vanguard mutual funds
- SEC EDGAR API integration with rate limiting
- Automated Vanguard fund discovery via `company_tickers_mf.json`
- Comprehensive batch reporting and progress tracking
- Local storage with metadata and summary logging

## Quick Start

### Prerequisites
- Python 3.8+
- Internet connection for SEC API access

### Installation

1. **Clone/Download the project**
   ```bash
   cd fund-prospectus-retriever
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   
   # Activate (Windows)
   venv\Scripts\activate
   
   # Activate (macOS/Linux)
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your email for SEC User-Agent header
   ```

### Usage Examples

#### Checkpoint 1: Single Fund Retrieval
```bash
# Retrieve VUSXX prospectus
python src/main.py --symbol VUSXX

# Retrieve any single fund
python src/main.py --symbol SPY

# Verbose logging
python src/main.py --symbol VUSXX --verbose
```

#### Checkpoint 2: Batch Vanguard Processing
```bash
# Process ALL Vanguard mutual funds
python src/main.py --batch-vanguard

# Test with limited number of funds
python src/main.py --batch-vanguard --max-funds 10

# Skip existing files (default behavior)
python src/main.py --batch-vanguard --skip-existing

# Force re-download all files
python src/main.py --batch-vanguard --force

# Dry run to see what would be processed
python src/main.py --batch-vanguard --dry-run
```

### Verification

After successful Checkpoint 2 execution:
```
data/
├── prospectuses/
│   ├── VUSXX/
│   │   ├── VUSXX_497K_20240315_*.html
│   │   └── VUSXX_497K_20240315_*.html.meta.json
│   ├── VTSAX/
│   ├── VTIAX/
│   ├── [100+ other Vanguard fund directories...]
│   ├── download_summary.json
│   └── vanguard_batch_results.json
└── logs/
    └── fund_retriever_20240320.log
```

## Architecture & Design Decisions

### Enhanced Modular Design for Batch Processing

```
src/
├── main.py                  # Entry point with batch processing support
├── sec_client.py           # SEC EDGAR API interactions
├── file_handler.py         # Enhanced storage with batch reporting
├── vanguard_processor.py   # NEW: Batch processing for Vanguard funds
├── models.py               # Data structures
└── utils.py                # Enhanced utilities and progress tracking
```

### New Checkpoint 2 Components

#### **VanguardFundProcessor**
- **Automated fund discovery**: Uses SEC's `company_tickers_mf.json`
- **Intelligent fund filtering**: Identifies Vanguard funds by title and ticker patterns
- **Batch processing**: Handles multiple funds with progress tracking
- **Comprehensive reporting**: Detailed success/failure statistics
- **Rate limiting**: Respects SEC API limits during batch operations

#### **Enhanced File Management**
- **Fund-specific directories**: Each fund gets its own subdirectory
- **Batch result tracking**: Comprehensive JSON reports for analysis
- **Progress monitoring**: Real-time progress updates during batch processing
- **Checkpoint tracking**: Records completion of different phases

### Vanguard Fund Identification Strategy

The system identifies Vanguard funds using multiple criteria:

#### **Title-Based Detection**
- Contains "VANGUARD" 
- Contains "VG " (Vanguard abbreviation)
- Contains "ADMIRAL" (Vanguard Admiral share class)

#### **Ticker Pattern Recognition**
- Starts with "V" and ends with "X" (e.g., VUSXX, VTSAX)
- 5-character tickers starting with "V" (e.g., VTIAX)

**Why this approach?**
- SEC doesn't explicitly tag funds by provider
- Multiple criteria ensure comprehensive coverage
- Pattern-based detection catches edge cases
- Minimizes false positives from other fund families

### Batch Processing Architecture

#### **Three-Phase Processing**
1. **Discovery Phase**: Fetch and filter Vanguard funds from SEC JSON
2. **Processing Phase**: Individual fund prospectus retrieval with progress tracking
3. **Reporting Phase**: Comprehensive statistics and result logging

#### **Error Handling & Recovery**
- **Individual fund failures** don't stop batch processing
- **Categorized error tracking** for analysis and debugging
- **Skip existing files** option for incremental processing
- **Detailed failure reporting** with specific error messages

#### **Performance Optimizations**
- **Rate limiting** between API calls to respect SEC requirements
- **Progress tracking** for long-running batch operations
- **Memory efficient** processing of large fund lists
- **Atomic operations** ensure data consistency

## Configuration

### Environment Variables (.env)
```bash
# SEC API Configuration
USER_AGENT=fund-retriever your.email@example.com  # Required by SEC
REQUEST_DELAY=0.1                                  # Rate limiting delay (increased for batch)
LOG_LEVEL=INFO                                     # DEBUG, INFO, WARNING, ERROR

# Storage Configuration  
DATA_DIR=./data                                    # Data storage location
```

### Batch Processing Settings
- **Rate Limiting**: 0.1s delay between requests (configurable)
- **Retry Logic**: Automatic retries for transient failures
- **Memory Management**: Streaming processing for large batches
- **Progress Updates**: Real-time progress logging

## Testing

### Unit Tests
```bash
# Run all tests including new batch processing tests
python -m pytest tests/ -v

# Test SEC client functionality
python tests/test_sec_client.py

# Test new Vanguard processor
python tests/test_vanguard_processor.py

# Run with coverage
python -m pytest tests/ --cov=src
```

### Manual Testing

#### **Checkpoint 1 Testing**
```bash
# Test single fund retrieval
python src/main.py --symbol VUSXX --verbose
python src/main.py --symbol VTSAX --verbose
```

#### **Checkpoint 2 Testing**
```bash
# Dry run to see fund list
python src/main.py --batch-vanguard --dry-run

# Test with small batch
python src/main.py --batch-vanguard --max-funds 5 --verbose

# Full batch processing
python src/main.py --batch-vanguard
```

## Checkpoint 2 Features

### **Automated Fund Discovery**
- Fetches latest `company_tickers_mf.json` from SEC
- Identifies 100+ Vanguard mutual funds automatically
- Filters out non-Vanguard funds using multiple criteria
- Sorts funds alphabetically for consistent processing

### **Batch Processing Capabilities**
- **Progress tracking**: Real-time progress updates with fund counts
- **Error resilience**: Individual failures don't stop the batch
- **Skip existing**: Option to skip already-downloaded prospectuses
- **Configurable limits**: Process subset of funds for testing
- **Dry run mode**: Preview what would be processed

### **Comprehensive Reporting**
```json
{
  "total_funds": 156,
  "successful_downloads": 142,
  "skipped_funds": 8,
  "failed_downloads": 6,
  "success_rate": 91.0,
  "total_size_bytes": 24567890,
  "form_type_distribution": {
    "497K": 89,
    "497": 34,
    "N-1A": 19
  },
  "error_categories": {
    "NO_PROSPECTUS": 4,
    "NETWORK_ERROR": 2
  }
}
```

### **Enhanced File Organization**
```
data/prospectuses/
├── VUSXX/                          # Money market funds
├── VTSAX/                          # Total stock market
├── VTIAX/                          # International equity
├── VBTLX/                          # Total bond market
├── [150+ other Vanguard funds...]
├── download_summary.json           # Master summary
└── vanguard_batch_results.json     # Batch processing details
```

## Edge Cases & Error Handling

### Checkpoint 2 Specific Challenges

**1. Large Scale Processing**
- **Issue**: Processing 150+ funds can take 30+ minutes
- **Solution**: Progress tracking, resumable processing, and skip-existing logic
- **Monitoring**: Real-time progress updates and estimated completion time

**2. SEC Rate Limiting at Scale**
- **Issue**: Batch processing can trigger rate limits
- **Solution**: Increased delays between requests and exponential backoff
- **Configuration**: Adjustable `REQUEST_DELAY` for different use cases

**3. Fund Identification Accuracy**
- **Issue**: False positives/negatives in Vanguard fund detection
- **Solution**: Multiple identification criteria with conservative patterns
- **Validation**: Manual review of fund list via dry-run mode

**4. Partial Batch Failures**
- **Issue**: Some funds may fail while others succeed
- **Solution**: Individual error tracking with categorized failure analysis
- **Recovery**: Skip-existing logic allows for easy re-runs

**5. Disk Space Management**
- **Issue**: 150 prospectuses can consume significant disk space
- **Solution**: File size monitoring and optional cleanup utilities
- **Monitoring**: Total size tracking in batch reports

### Vanguard-Specific Considerations

**1. Fund Family Diversity**
- Vanguard has 150+ mutual funds across all asset classes
- Different funds use different form types (497K, 497, N-1A)
- Some funds have multiple share classes

**2. Filing Patterns**
- Money market funds (like VUSXX) update frequently
- Index funds typically have fewer updates
- Active funds may have more frequent prospectus updates

**3. Data Quality Variations**
- Some older or less common funds may have limited prospectus availability
- International funds may have different filing requirements
- ETF vs. mutual fund differences in filing patterns

## Monitoring & Observability

### Enhanced Logging for Batch Processing
- **Batch-level metrics**: Overall success rates and timing
- **Fund-level details**: Individual fund processing results
- **Error categorization**: Automated error analysis and reporting
- **Performance tracking**: Processing speed and resource utilization

### Checkpoint 2 Monitoring
```bash
# Monitor batch processing in real-time
tail -f data/logs/fund_retriever_*.log

# View batch results summary
cat data/prospectuses/vanguard_batch_results.json | python -m json.tool

# Check processing statistics
python -c "
from src.file_handler import FileHandler
fh = FileHandler()
stats = fh.get_batch_summary_stats()
print(f'Total downloads: {stats[\"total_downloads\"]}')
print(f'Unique funds: {stats[\"unique_funds\"]}')
print(f'Total size: {stats[\"total_size_bytes\"]:,} bytes')
"
```

### Key Metrics Tracked
- **Batch completion time**: Total time for full Vanguard processing
- **Success/failure rates**: Overall and per-fund-type success rates
- **Data volume**: Total bytes downloaded and per-fund averages
- **Error patterns**: Common failure modes and their frequencies
- **Form type distribution**: Which SEC forms are most common

## Future Extensibility (Checkpoint 3)

The Checkpoint 2 architecture provides excellent foundation for Checkpoint 3:

### **Arbitrary Fund Provider Support**
- **Modular processor design**: Easy to create `FidelityProcessor`, `SchwabProcessor`, etc.
- **Generic fund identification**: Framework for non-pattern-based fund discovery
- **Provider abstraction**: Common interface for different fund families

### **Enhanced Form Type Handling**
- **ETF support**: Different forms (497 vs 497K) for different fund types
- **International funds**: Special handling for foreign fund filings
- **Alternative structures**: Support for UITs, closed-end funds, etc.

### **Advanced Error Recovery**
- **Retry strategies**: Different retry logic for different error types
- **Alternative data sources**: Fallback to fund company websites
- **Manual intervention**: Framework for handling edge cases

## Troubleshooting

### Checkpoint 2 Specific Issues

**1. Batch Processing Hangs**
```bash
# Check for network issues
curl -H "User-Agent: test-client test@example.com" \
  "https://data.sec.gov/files/company_tickers_mf.json"

# Monitor progress with verbose logging
python src/main.py --batch-vanguard --max-funds 5 --verbose
```

**2. High Failure Rates**
```bash
# Analyze error patterns
grep "ERROR" data/logs/fund_retriever_*.log | tail -20

# Check specific fund failures
cat data/prospectuses/vanguard_batch_results.json | jq '.results[] | select(.success == false)'
```

**3. Disk Space Issues**
```bash
# Check current usage
du -sh data/prospectuses/

# Clean up old files if needed
find data/prospectuses/ -name "*.html" -mtime +30 -type f
```

**4. Memory Issues with Large Batches**
```bash
# Process in smaller chunks
python src/main.py --batch-vanguard --max-funds 25
# Then increase limit gradually
```

## Success Criteria

### Checkpoint 1
- Successfully retrieves VUSXX prospectus
- Saves HTML/PDF file with proper metadata
- Comprehensive logs with metadata tracking
- Graceful handling of edge cases

### Checkpoint 2
- **Automated discovery**: Uses `company_tickers_mf.json` to find all Vanguard funds
- **Batch processing**: Processes 100+ Vanguard mutual funds
- **Progress tracking**: Real-time progress updates during processing
- **Comprehensive logging**: Detailed success/failure summary
- **Error resilience**: Individual failures don't stop batch processing
- **Organized storage**: Fund-specific directories with metadata
- **Performance optimization**: Rate limiting and memory efficiency
- **Extensible architecture**: Ready for Checkpoint 3 arbitrary fund retrieval