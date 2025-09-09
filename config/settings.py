import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # SEC API Configuration
    SEC_API_BASE_URL = os.getenv('SEC_API_BASE_URL', 'https://www.sec.gov/Archives/edgar')
    USER_AGENT = os.getenv('USER_AGENT', 'fund-retriever contact@yourcompany.com')
    REQUEST_DELAY = float(os.getenv('REQUEST_DELAY', '0.1'))
    
    # Storage Configuration
    PROJECT_ROOT = Path(__file__).parent.parent
    DATA_DIR = PROJECT_ROOT / 'data'
    PROSPECTUS_DIR = DATA_DIR / 'prospectuses'
    LOG_DIR = DATA_DIR / 'logs'
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    @classmethod
    def ensure_directories(cls):
        """Create necessary directories if they don't exist"""
        cls.DATA_DIR.mkdir(exist_ok=True)
        cls.PROSPECTUS_DIR.mkdir(exist_ok=True)
        cls.LOG_DIR.mkdir(exist_ok=True)

settings = Settings()