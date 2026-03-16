from functools import wraps
from django.http import JsonResponse
from .x402 import build_payment_required_header, verify_payment_signature
from .models import PaymentReceipt
import json, base64

def x402_required(get_pay_to, get_amounts, description="", bypass_cache=False):
    """
    Decorator to gate views with x402 Payment Required.
    
    get_pay_to: callable(request, **kwargs) -> str (recipient STX address)
    get_amounts: callable(request, **kwargs) -> (int amountSTX, int amountUSDCx[, int amountSBTC])
    bypass_cache: bool - if True, skip checking for existing PaymentReceipt (default False)
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Check for existing valid receipt in DB if user is authenticated
            if request.user.is_authenticated and not bypass_cache:
                # We need to know what 'resource' this is in terms of our Receipt model
                # Defaults to using the URL path and generic resource type unless overridden
                resource_type = kwargs.get("resource_type", "generic")
                resource_id = str(kwargs.get("resource_id") or kwargs.get("pk") or kwargs.get("id") or request.path)
                
                receipt = PaymentReceipt.objects.filter(
                    user=request.user,
                    resource_type=resource_type,
                    resource_id=resource_id,
                ).first()
                
                if receipt:
                    # Provide tx_id to the view even if cached
                    request.x402_tx_id = receipt.tx_id
                    return view_func(request, *args, **kwargs)

            # Check for payment-signature in headers
            sig = request.headers.get("payment-signature")
            pay_to = get_pay_to(request, **kwargs)
            
            # Support both 2-value and 3-value returns from get_amounts
            amounts = get_amounts(request, **kwargs)
            if len(amounts) == 3:
                amount_stx, amount_usdcx, amount_sbtc = amounts
            else:
                amount_stx, amount_usdcx = amounts
                amount_sbtc = 0
            
            resource = request.path

            if not sig:
                # Challenge with 402 and the payment-required header
                header = build_payment_required_header(
                    pay_to, amount_stx, amount_usdcx, resource, description, amount_sbtc
                )
                resp = JsonResponse({"detail": "Payment required"}, status=402)
                resp["payment-required"] = header
                # Ensure headers are exposed for CORS
                resp["Access-Control-Expose-Headers"] = "payment-required"
                return resp

            # Decode payment-signature to extract txId and metadata
            try:
                sig_data = json.loads(base64.b64decode(sig))
                tx_id = sig_data.get("txId", "")
                token_type = sig_data.get("tokenType", "STX")
                sender_address = sig_data.get("senderAddress", "")
            except (json.JSONDecodeError, Exception):
                tx_id = ""
                token_type = "STX"
                sender_address = ""

            # Verify the signature via facilitator
            expected_amounts = {
                'stx': amount_stx,
                'usdcx': amount_usdcx,
                'sbtc': amount_sbtc
            }
            result = verify_payment_signature(sig, pay_to, resource, expected_amounts)
            verified_tx_id = result.get("txId") or tx_id
            
            if not result.get("verified"):
                return JsonResponse({"detail": "Payment verification failed", "error": result.get("error")}, status=402)

            # Provide the tx_id to the underlying view
            request.x402_tx_id = verified_tx_id
            request.x402_token_type = result.get("tokenType") or token_type

            # Record receipt in DB
            if request.user.is_authenticated:
                resource_type = kwargs.get("resource_type", "generic")
                resource_id = str(kwargs.get("pk") or kwargs.get("id") or request.path)
                
                PaymentReceipt.objects.get_or_create(
                    user=request.user,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    defaults={
                        "tx_id": verified_tx_id,
                        "token_type": result.get("tokenType") or token_type,
                        "amount": result.get("amount", 0),
                        "receipt_token": result.get("receiptToken", ""),
                    }
                )

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

