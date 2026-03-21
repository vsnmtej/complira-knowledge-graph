"""
Unit test configuration for ingestion module.

Suppresses urllib3 SSL warning that fires on Python 3.9 / LibreSSL environments
when importing the arango client library. This is an environment-level issue
(LibreSSL < 1.1.1 on macOS system Python) that is irrelevant to unit test logic.
"""

import warnings

# Suppress the urllib3 NotOpenSSLWarning that fires on Python 3.9 with LibreSSL.
# This must be set before pytest's filterwarnings="error" applies (via autouse),
# so we use warnings.filterwarnings directly here at module import time.
warnings.filterwarnings(
    "ignore",
    message="urllib3 v2 only supports OpenSSL",
    category=Warning,
)
