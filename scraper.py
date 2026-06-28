#!/usr/bin/env python3
"""
Scrape wallet addresses from recent token transactions for airdrop targeting.
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.config import CHAIN_CONFIG, DEFAULT_CHAIN
from web3 import Web3

def get_recent_interactors(token_address, chain_name=DEFAULT_CHAIN, tx_count=500):
    """Get unique addresses that interacted with a token recently."""
    config = CHAIN_CONFIG[chain_name]
    w3 = Web3(Web3.HTTPProvider(config["rpc"]))
    
    if chain_name in ("bsc", "polygon", "avalanche"):
        from web3.middleware import geth_poa_middleware
        w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    
    token = Web3.to_checksum_address(token_address)
    current_block = w3.eth.block_number
    from_block = max(0, current_block - 10000)  # ~2 days back
    
    addresses = set()
    
    # Transfer event signature
    transfer_abi = [{
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event"
    }]
    
    contract = w3.eth.contract(address=token, abi=transfer_abi)
    
    # Get recent Transfer events
    for start in range(from_block, current_block, 2000):
        end = min(start + 2000, current_block)
        try:
            events = contract.events.Transfer.get_logs(fromBlock=start, toBlock=end)
            for e in events:
                frm = e["args"]["from"]
                to = e["args"]["to"]
                if frm != "0x0000000000000000000000000000000000000000":
                    addresses.add(frm)
                if to != "0x0000000000000000000000000000000000000000":
                    addresses.add(to)
        except:
            continue
    
    return list(addresses)

if __name__ == "__main__":
    # USDC on Ethereum
    addrs = get_recent_interactors("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
    print(f"Found {len(addrs)} addresses")
    
    # Save to file for airdrop
    with open("targets.json", "w") as f:
        json.dump(addrs, f, indent=2)
    
    # Format for the admin panel (one per line)
    with open("targets.txt", "w") as f:
        f.write("\n".join(addrs))
    
    print("Saved to targets.txt — paste this into the Airdrop tab")