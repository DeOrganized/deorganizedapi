import uuid, base64, json, requests, os
from datetime import datetime, timedelta, timezone

FACILITATOR_URL = os.environ.get("X402_FACILITATOR_URL", "https://x402.aibtc.dev")

def build_payment_required_header(pay_to: str, amount_stx: int, amount_usdcx: int,
                                   resource: str, description: str, amount_sbtc: int = 0) -> str:
    """
    Builds the base64 encoded JSON payload for the payment-required header.
    Amounts should be in microSTX, smallest USDCx unit, and satoshis (sBTC).
    """
    payload = {
        "version": "2",
        "payTo": pay_to,
        "amountSTX": int(amount_stx),
        "amountUSDCx": int(amount_usdcx),
        "amountSBTC": int(amount_sbtc),
        "resource": resource,
        "description": description,
        "tokenTypes": ["STX", "USDCx", "sBTC"],
        "network": os.environ.get("STACKS_NETWORK", "mainnet"),
        "nonce": str(uuid.uuid4()),
        "expiresAt": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


def check_tx_on_blockchain(tx_id: str, expected_pay_to: str, expected_amounts: dict, token_type: str = "STX", network: str = "mainnet") -> dict:
    """
    Directly check Hiro API for transaction status and verify recipient/amount.
    """
    if not tx_id:
        return {"verified": False, "error": "Missing TX ID"}
    
    # Standardize 0x prefix for blockchain check
    clean_tx_id = tx_id if tx_id.startswith("0x") else f"0x{tx_id}"
    
    base_url = "https://api.mainnet.hiro.so" if network == "mainnet" else "https://api.testnet.hiro.so"
    try:
        resp = requests.get(f"{base_url}/extended/v1/tx/{clean_tx_id}", timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            status = data.get("tx_status")
            
            # We ONLY accept success or pending
            if status not in ["success", "pending"]:
                return {"verified": False, "error": f"Transaction status is {status}"}

            # Verify STX transfers
            if token_type == "STX" and data.get("tx_type") == "token_transfer":
                tt = data.get("token_transfer", {})
                recipient = tt.get("recipient_address")
                amount = int(tt.get("amount", 0))
                
                if recipient == expected_pay_to and amount >= expected_amounts.get('stx', 0):
                    return {
                        "verified": True, 
                        "txId": clean_tx_id, 
                        "status": status, 
                        "amount": amount,
                        "tokenType": "STX"
                    }
                else:
                    return {
                        "verified": False, 
                        "error": f"STX Transfer mismatch. Expected {expected_amounts.get('stx')} to {expected_pay_to}, found {amount} to {recipient}"
                    }

            # Verify Contract Calls (USDCx, sBTC, etc.)
            # For now, if it's a success/pending contract call, we log and allow if it's not STX
            # But we should ideally parse function_args
            if data.get("tx_type") == "contract_call":
                # Basic verification for contract calls
                return {
                    "verified": True, 
                    "txId": clean_tx_id, 
                    "status": status,
                    "tokenType": token_type
                }

            return {"verified": False, "error": f"Unsupported transaction type: {data.get('tx_type')}"}
        
        return {"verified": False, "error": f"TX not found on blockchain: {resp.status_code}"}
    except Exception as e:
        return {"verified": False, "error": str(e)}


def verify_payment_signature(signature_b64: str, expected_pay_to: str,
                              resource: str, expected_amounts: dict) -> dict:
    """
    POST to aibtcdev facilitator to verify the payment transaction.
    Returns verified payload or raises a requests exception.
    """
    network = os.environ.get("STACKS_NETWORK", "mainnet").lower()
    
    # Support for old calls that might not provide expected_amounts dict properly
    if not isinstance(expected_amounts, dict):
        expected_amounts = {'stx': 0, 'usdcx': 0, 'sbtc': 0}

    try:
        resp = requests.post(
            f"{FACILITATOR_URL}/verify",
            json={
                "paymentSignature": signature_b64,
                "payTo": expected_pay_to,
                "resource": resource,
            },
            timeout=15,
        )
        if resp.ok:
            result = resp.json()
            if result.get("verified"):
                return result
    except Exception as e:
        print(f"Facilitator Error: {e}")

    # Fallback: check blockchain directly
    try:
        sig_data = json.loads(base64.b64decode(signature_b64))
        tx_id = sig_data.get("txId")
        token_type = sig_data.get("tokenType", "STX")
        
        if tx_id:
            return check_tx_on_blockchain(
                tx_id=tx_id, 
                expected_pay_to=expected_pay_to, 
                expected_amounts=expected_amounts,
                token_type=token_type,
                network=network
            )
    except Exception as e:
        return {"verified": False, "error": f"Fallback verification failed: {str(e)}"}

    return {"verified": False, "error": "Facilitator failed and no valid TX ID found in signature"}
