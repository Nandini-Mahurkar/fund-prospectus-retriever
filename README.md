# Fund Prospectus Retriever

A Python automation system that retrieves mutual fund and ETF prospectuses from the SEC EDGAR database. This implementation covers the third checkpoint

## Project Overview

This system accepts fund symbols and automatically retrieves the most recent prospectus filings from the SEC EDGAR API, saving them locally with comprehensive metadata tracking.

### Current Status: All Checkpoints Complete

* **Checkpoint 1**: Single fund retrieval (VUSXX)
* **Checkpoint 2**: Batch processing for all Vanguard mutual funds
* **Checkpoint 3**: Arbitrary fund retrieval (any fund symbol)
* SEC EDGAR API integration with enhanced form type handling
* Multi-strategy fund discovery (mutual funds, ETFs, direct CIK lookup)
* Support for supplements and amendments
* Comprehensive error handling and fallback strategies

## Quick Start

### Prerequisites

* Python 3.8+
* Internet connection for SEC API access

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


#### Checkpoint 3: Arbitrary Fund Retrieval

```bash
# Single arbitrary fund
python src/main.py --arbitrary SPY
python src/main.py --arbitrary QQQ
python src/main.py --arbitrary IWM

# Multiple arbitrary funds
python src/main.py --arbitrary-batch SPY QQQ IWM VTI EFA

# Mixed ETFs and mutual funds
python src/main.py --arbitrary-batch SPY VTSAX QQQ FXAIX

# Test with limited batch
python src/main.py --arbitrary-batch SPY QQQ IWM --max-funds 5 --verbose

# Dry run for arbitrary funds
python src/main.py --arbitrary-batch SPY QQQ --dry-run
```

### Expected Results

After successful execution:

```
data/
├── prospectuses/
│   ├── SPY/                            # ETFs
│   │   ├── SPY_497_20240315_*.html
│   │   └── SPY_497_20240315_*.html.meta.json
│   ├── QQQ/                            # Invesco ETFs
│   ├── VUSXX/                          # Vanguard mutual funds  
│   ├── VTSAX/
│   ├── [150+ other fund directories...]
│   ├── download_summary.json
│   ├── vanguard_batch_results.json     # Checkpoint 2 results
│   └── arbitrary_batch_results.json    # Checkpoint 3 results
└── logs/
    └── fund_retriever_20240320.log
```

## Architecture & Design Decisions

### Enhanced Architecture for All Fund Types

```
src/
├── main.py                     # Entry point with all checkpoint support
├── sec_client.py              # Enhanced SEC EDGAR API client
├── file_handler.py            # Storage with batch reporting
├── generic_fund_processor.py  # NEW: Checkpoint 3: Arbitrary fund processing
├── models.py                  # Data structures
└── utils.py                   # Utilities and progress tracking
```

### Checkpoint 3: Arbitrary Fund Processing

#### Multi-Strategy Fund Discovery

The system uses a cascade of discovery methods to handle any fund symbol:

1. **SEC Mutual Fund JSON**: Check company\_tickers\_mf.json for mutual funds
2. **Known ETF Database**: Built-in database of popular ETFs with providers
3. **Pattern-Based Detection**: Recognize provider patterns (SPY→SPDR, QQQ→Invesco)
4. **Direct CIK Lookup**: Handle numeric CIK inputs directly
5. **Fallback Strategies**: Pattern matching for unknown funds

#### Enhanced Form Type Handling

Different fund types use different SEC forms:

* **Mutual Funds**: Prioritize 497K → 497 → N-1A
* **ETFs**: Prioritize 497 → 497K → N-1A (QQQ often uses 497)
* **All Types**: Support supplements and amendments

#### Provider-Specific Optimizations

* **QQQ Special Handling**: Invesco QQQ prefers Form 497 over 497K
* **SPDR Recognition**: SPY, XL series, sector ETFs
* **iShares Patterns**: IWM, EFA, international ETFs

### Fund Type Support Matrix

| Fund Family  | Mutual Funds | ETFs    | Examples               | Primary Forms   |
| ------------ | ------------ | ------- | ---------------------- | --------------- |
| **Vanguard** | Yes          | Yes     | VUSXX, VTSAX, VTI, VOO | 497K, 497, N-1A |
| **Fidelity** | Yes          | Partial | FXAIX, FZROX           | 497K, 497       |
| **SPDR**     | No           | Yes     | SPY, XLF, GLD          | 497, N-1A       |
| **iShares**  | No           | Yes     | IWM, EFA, TLT          | 497, N-1A       |
| **Invesco**  | Partial      | Yes     | QQQ, QQQM              | 497, 497K       |
| **Schwab**   | Yes          | Yes     | SCHW series            | 497K, 497       |
| **ARK**      | No           | Yes     | ARKK, ARKQ             | 497             |

Legend: Yes = Full Support, Partial = Partial Support, No = Not Applicable

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

## Testing

### Unit Tests

```bash
# Run all tests including Checkpoint 3
python -m pytest tests/ -v

# Test individual components
python tests/test_generic_processor.py        # Checkpoint 3

# Run with coverage
python -m pytest tests/ --cov=src
```

### Manual Testing

#### Checkpoint 1 Testing

```bash
python src/main.py --symbol VUSXX --verbose
python src/main.py --symbol VTSAX --verbose
```

#### Checkpoint 2 Testing

```bash
python src/main.py --batch-vanguard --dry-run
python src/main.py --batch-vanguard --max-funds 5
```

#### Checkpoint 3 Testing

```bash
# Test popular ETFs
python src/main.py --arbitrary SPY --verbose
python src/main.py --arbitrary QQQ --verbose
python src/main.py --arbitrary IWM --verbose

# Test mixed fund types
python src/main.py --arbitrary-batch SPY VTSAX QQQ --verbose

# Test less common funds
python src/main.py --arbitrary-batch GLD TLT EFA
```

## Checkpoint 3 Features

### Universal Fund Symbol Support

* **Popular ETFs**: SPY, QQQ, IWM, VTI, VOO, EFA, GLD, TLT
* **Mutual Funds**: VUSXX, VTSAX, FXAIX, any V****X or F****X pattern
* **Alternative Formats**: Direct CIK numbers, numeric identifiers
* **Provider Agnostic**: Works across Vanguard, Fidelity, SPDR, iShares, Invesco

### Intelligent Form Type Selection

The system automatically selects appropriate forms based on fund type:

```json
{
  "fund_type": "ETF",
  "symbol": "QQQ",
  "provider": "Invesco",
  "preferred_forms": ["497", "497K", "N-1A"],
  "discovery_method": "Known ETF Database"
}
```

### Enhanced Error Handling

```json
{
  "fund_symbol": "UNKNOWN",
  "success": false,
  "error_category": "DISCOVERY_FAILED",
  "error_message": "Could not discover fund information using any strategy",
  "strategies_attempted": [
    "SEC Mutual Fund JSON",
    "Known ETF Database", 
    "Direct CIK Lookup",
    "Pattern Matching"
  ]
}
```

### Supplements and Amendments

The system detects and logs supplement filings:

* Identifies amendments (forms ending with 'A')
* Detects supplements filed within 30 days
* Logs supplement count but uses main prospectus
* Future enhancement: combine supplements with main document

## Edge Cases & Advanced Error Handling

### Checkpoint 3 Specific Challenges

**1. Fund Type Ambiguity**

* **Issue**: Same ticker could be ETF and mutual fund share classes
* **Solution**: ETF patterns take precedence, form type validation
* **Example**: VTI (ETF) vs VTSMX (mutual fund equivalent)

**2. Multiple Fund Families**

* **Issue**: Some tickers exist across providers
* **Solution**: Pattern-based provider detection with priority ordering
* **Fallback**: Use most recent filing regardless of provider

**3. International and Complex Funds**

* **Issue**: Foreign funds, currency hedged funds have different filing patterns
* **Solution**: Extended form type support (S-1, S-3, N-14)
* **Monitoring**: Log unusual form types for analysis

**4. Delisted or Merged Funds**

* **Issue**: Fund symbols may no longer be active
* **Solution**: Historical filing search with clear error messages
* **User Guidance**: Suggest checking fund status independently

**5. Rate Limiting at Scale**

* **Issue**: Processing many arbitrary funds can trigger limits
* **Solution**: Enhanced rate limiting with backoff strategies
* **Configuration**: Adjustable delays based on batch size

### QQQ-Specific Handling

Since QQQ was mentioned specifically in the requirements:

```python
# QQQ uses Form 497 instead of typical 497K
if provider == "Invesco" and fund_symbol.upper() == "QQQ":
    # Prioritize Form 497 over 497K for QQQ
    form_priority = ['497', '497K', 'N-1A']
```

### Supplements Decision

**Current Implementation**: Log supplements but use main prospectus
**Rationale**:

* Main prospectus contains complete fund information
* Supplements often contain minor updates or corrections
* Combining documents requires complex parsing logic
* Users can access supplement information via metadata logs

**Future Enhancement**: Optional supplement combination with user flag

## Monitoring & Observability

### Enhanced Metrics for Checkpoint 3

* **Discovery Success Rate**: By strategy and fund type
* **Provider Coverage**: Success rates by fund family
* **Form Type Distribution**: Which forms are most common
* **Processing Time**: Average time by fund type and discovery method

### Checkpoint 3 Monitoring

```bash
# View arbitrary fund processing results
cat data/prospectuses/arbitrary_batch_results.json | python -m json.tool

# Discovery method analysis
python -c "
import json
with open('data/prospectuses/arbitrary_batch_results.json') as f:
    data = json.load(f)
methods = {}
for result in data['results']:
    method = result.get('discovery_method', 'Unknown')
    methods[method] = methods.get(method, 0) + 1
for method, count in sorted(methods.items()):
    print(f'{method}: {count} funds')
"

# Error category analysis
python -c "
import json
with open('data/prospectuses/arbitrary_batch_results.json') as f:
    data = json.load(f)
errors = {}
for result in data['results']:
    if not result['success']:
        cat = result.get('error_category', 'OTHER')
        errors[cat] = errors.get(cat, 0) + 1
for cat, count in sorted(errors.items()):
    print(f'{cat}: {count} funds')
"
```
