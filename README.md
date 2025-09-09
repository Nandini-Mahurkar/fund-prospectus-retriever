# Fund Prospectus Retriever - Checkpoint 1

A Python automation system that retrieves mutual fund prospectuses from the SEC EDGAR database. This implementation covers **Checkpoint 1**: single fund retrieval for VUSXX.

## Project Overview

This system accepts a fund symbol (e.g., VUSXX) and automatically retrieves the most recent prospectus filing from the SEC EDGAR API, saving it locally with comprehensive metadata tracking.

## Setup

### Prerequisites
- Python 3.8+
- Internet connection for SEC API access

### Installation

1. **Navigate to project directory**
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

5. **Run the system**
   ```bash
   # Default: retrieve VUSXX prospectus
   python src/main.py
   
   # With custom symbol
   python src/main.py --symbol VUSXX
   
   # With verbose logging
   python src/main.py --symbol VUSXX --verbose
   ```

### Expected Output

After successful execution:
```
data/
├── prospectuses/
│   └── VUSXX/
│       ├── VUSXX_497K_20240315_000086208424000012.html
│       └── VUSXX_497K_20240315_000086208424000012.html.meta.json
├── logs/
│   └── fund_retriever_20240320.log
└── download_summary.json
```

## Architecture

### Modular Design

```
src/
├── main.py          # Entry point and CLI interface
├── sec_client.py    # SEC EDGAR API interactions
├── file_handler.py  # Local storage management
├── models.py        # Data structures
└── utils.py         # Shared utilities and logging
```

Design principles:
- **Separation of concerns**: Each module has a single responsibility
- **Testability**: Components can be unit tested in isolation
- **Extensibility**: Easy to add new fund providers or storage backends
- **Maintainability**: Clear interfaces between components

### SEC API Integration

#### CIK Discovery Strategy
The system uses a cascade approach to find the fund's Central Index Key (CIK):

1. **Direct API lookup**: Try SEC data API with symbol
2. **Mutual fund tickers**: Search `company_tickers_mf.json`
3. **Hardcoded fallbacks**: Known CIKs for common funds (VUSXX → Vanguard)

SEC doesn't provide unified symbol-to-CIK mapping. Different fund types are listed in different places. Fallbacks ensure reliability for common cases.

#### Form Type Prioritization
The system prioritizes prospectus forms in this order:
1. **497K** - Summary prospectuses (most current)
2. **497** - General prospectus filings
3. **N-1A** - Registration statements
4. **485BPOS/485APOS** - Post-effective amendments

497K forms contain the most recent investor-facing information. Different fund types use different form types.

### File Storage

#### Directory Structure
```
data/prospectuses/
├── VUSXX/                    # Fund-specific directories
│   ├── [fund]_[form]_[date]_[accession].html
│   └── [filename].meta.json  # Metadata alongside each file
└── download_summary.json     # Master log of all downloads
```

Benefits:
- **Fund isolation**: Easy to find all documents for a specific fund
- **Metadata tracking**: Rich information for auditing and analysis
- **Collision avoidance**: Unique filenames prevent overwrites
- **Scalability**: Structure works for thousands of funds

#### Filename Convention
`VUSXX_497K_20240315_000086208424000012.html`

Components:
- **Symbol**: Fund identifier
- **Form type**: SEC form category
- **Date**: Filing date (YYYYMMDD)
- **Accession**: Unique SEC filing identifier
- **Extension**: Document type (.html/.pdf)

## Configuration

### Environment Variables (.env)
```bash
# SEC API Configuration
USER_AGENT=fund-retriever your.email@example.com  # Required by SEC
REQUEST_DELAY=0.1                                  # Rate limiting delay
LOG_LEVEL=INFO                                     # DEBUG, INFO, WARNING, ERROR

# Storage Configuration  
DATA_DIR=./data                                    # Data storage location
```

**Important**: The SEC requires a descriptive User-Agent header with contact information. Update the `USER_AGENT` in your `.env` file with your actual email address.

## Testing

### Unit Tests
```bash
# Run all tests
python -m pytest tests/test_sec_client.py -v

# Run specific test
python tests/test_sec_client.py TestSECClient.test_get_latest_prospectus_success

# Run with coverage
python -m pytest tests/test_sec_client.py --cov=src.sec_client
```

### Manual Testing
```bash
# Test with different symbols
python src/main.py --symbol VUSXX

# Test error handling
python src/main.py --symbol INVALID123
```

## Edge Cases and Error Handling

### SEC API Challenges

**Rate Limiting**
- SEC enforces rate limits (10 requests/second)
- Built-in delays between requests (`REQUEST_DELAY`)
- Logs request timing and rate limit errors

**CIK Discovery Failures**
- Fund symbols aren't consistently mapped to CIKs
- Multiple lookup strategies with fallbacks
- VUSXX uses hardcoded Vanguard CIK as ultimate fallback

**Form Type Variations**
- Different funds use different prospectus forms
- Flexible form type detection with prioritization
- Handles 497, 497K, N-1A, 485BPOS, 485APOS

**Document Availability**
- Some filings may be unavailable or corrupted
- Validation of downloaded content and graceful fallback
- Clear error messages for debugging

### Data Quality Issues

**Invalid Fund Symbols**
- Regex-based symbol validation
- Automatic uppercase conversion and cleaning
- Clear error messages for invalid inputs

**Date Parsing**
- SEC uses multiple date formats across different APIs
- Multiple date format parsers with fallbacks
- Supports YYYY-MM-DD, MM/DD/YYYY, YYYYMMDD, etc.

**File Integrity**
- Content-length validation and SHA256 hashing
- Automatic retry with exponential backoff
- Metadata includes file integrity checks

### Network and Infrastructure

**Connection Failures**
- Automatic retries with exponential backoff
- Reasonable timeouts to prevent hanging
- Clear error messages without crashes

**Storage Management**
- File size tracking and logging
- Optional cleanup utility for old files
- Pre-flight disk space checks

**Concurrent Access**
- Safe concurrent access to data files
- Atomic operations (downloads complete or fail)
- JSON metadata written atomically

### VUSXX-Specific Considerations

**Money Market Fund Characteristics**
- VUSXX is a money market fund with frequent filing updates
- Typically uses 497K forms for prospectus updates
- Filed under Vanguard Group (CIK: 0000862084)

**Filing Patterns**
- Updates are often quarterly or when NAV/yield changes significantly
- May include supplements and amendments
- Document format is typically HTML with embedded tables

**Fallback Strategy**
If automatic discovery fails for VUSXX:
1. Uses hardcoded Vanguard CIK (0000862084)
2. Searches recent filings for money market fund patterns
3. Prioritizes 497K forms over other types
4. Validates content contains VUSXX-specific information

## Monitoring

### Logging Strategy
- **File logs**: Detailed logs in `data/logs/fund_retriever_YYYYMMDD.log`
- **Console output**: User-friendly progress and results
- **Structured data**: JSON metadata for programmatic analysis
- **Performance metrics**: Request timing and file size tracking