#!/usr/bin/env python3
"""Solana helper utilities for wallet checks and devnet/testnet testing."""
import os
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.config import CHAIN_CONFIG, SOLANA_PRIVATE_KEY, SOLANA_WALLET_ADDRESS, SOLANA_RPC

try:
    import base58
    from solana.rpc.api import Client as SolanaClient
    from solana.rpc.commitment import Confirmed
    from solana.keypair import Keypair
    from solana.publickey import PublicKey
    from solana.transaction import Transaction
    from solana.system_program import transfer as sol_transfer
    from solana.system_program import TransferParams
    HAS_SOLANA = True
except ImportError:
    HAS_SOLANA = False
    print("[!] Solana libraries not installed. Run: pip install solana spl-token base58")


class SolanaHelper:
    def __init__(self, chain_name="solana_devnet"):
        self.chain_name = chain_name
        self.config = CHAIN_CONFIG.get(chain_name)
        if not self.config:
            raise ValueError(f"Unknown Solana chain: {chain_name}")

        self.rpc_url = self.config["rpc"]
        if SOLANA_RPC:
            self.rpc_url = SOLANA_RPC

        self.client = SolanaClient(self.rpc_url)
        self.wallet_address = SOLANA_WALLET_ADDRESS
        self.keypair = None
        if SOLANA_PRIVATE_KEY:
            try:
                raw = base58.b58decode(SOLANA_PRIVATE_KEY)
                self.keypair = Keypair.from_secret_key(raw[:32])
                self.wallet_address = str(self.keypair.public_key)
            except Exception as e:
                raise ValueError(f"Invalid SOLANA_PRIVATE_KEY: {e}")

    def is_connected(self):
        try:
            return self.client.is_connected()
        except Exception:
            return False

    def get_balance(self, address=None):
        if address is None:
            address = self.wallet_address
        pubkey = PublicKey(address)
        resp = self.client.get_balance(pubkey, commitment=Confirmed)
        lamports = resp["result"]["value"]
        return lamports, lamports / 1e9

    def send_sol(self, to_address, amount_sol):
        if not self.keypair:
            raise ValueError("SOLANA_PRIVATE_KEY is required to send SOL")
        payer = self.keypair
        recipient = PublicKey(to_address)
        lamports = int(amount_sol * 1e9)
        txn = Transaction()
        txn.add(sol_transfer(TransferParams(from_pubkey=payer.public_key, to_pubkey=recipient, lamports=lamports)))
        resp = self.client.send_transaction(txn, payer)
        return resp

    def create_new_keypair(self):
        kp = Keypair()
        secret = base58.b58encode(bytes(kp.seed)).decode()
        return {
            "address": str(kp.public_key),
            "secret_base58": secret,
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Solana helper for devnet/testnet testing")
    parser.add_argument("--chain", default="solana_devnet", help="Solana chain: solana_devnet, solana_testnet, solana")
    parser.add_argument("--check", help="Check wallet balance")
    parser.add_argument("--send-sol", help="Send SOL to target address")
    parser.add_argument("--amount", type=float, default=0.001, help="Amount of SOL to send")
    parser.add_argument("--new-keypair", action="store_true", help="Generate a new Solana keypair")
    args = parser.parse_args()

    if not HAS_SOLANA:
        print("[!] Install Solana dependencies: pip install solana spl-token base58")
        sys.exit(1)

    helper = SolanaHelper(chain_name=args.chain)
    print(f"[+] Connected to {args.chain} at {helper.rpc_url}: {helper.is_connected()}")
    if helper.wallet_address:
        print(f"[+] Local wallet: {helper.wallet_address}")

    if args.new_keypair:
        kp = helper.create_new_keypair()
        print(json.dumps(kp, indent=2))
        return

    if args.check:
        lamports, sol = helper.get_balance(args.check)
        print(f"Balance for {args.check}: {sol:.9f} SOL ({lamports} lamports)")
        return

    if args.send_sol:
        result = helper.send_sol(args.send_sol, args.amount)
        print(json.dumps(result, indent=2))
        return

    print("No action specified. Use --check, --send-sol, or --new-keypair.")


if __name__ == "__main__":
    main()
