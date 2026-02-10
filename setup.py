"""Setup configuration for autotrade package."""
from setuptools import setup, find_packages

setup(
    name="autotrade",
    version="0.1.0",
    description="Automated trading bot for daily/swing trading strategies",
    author="Your Name",
    packages=find_packages(),
    install_requires=[
        "schwab-py>=0.0.0a25",
        "pandas>=2.2.0",
        "selenium>=4.17.0",
        "yfinance>=0.2.30",
        "numpy>=1.26.0",
    ],
    python_requires=">=3.11",
)
