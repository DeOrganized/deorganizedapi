"""
DAP credit rewards system.

Rewards are defined in DAP_REWARDS. Each entry specifies an amount,
description, and whether it is one-time (default) or repeatable.

To add a new reward:
1. Add an entry to DAP_REWARDS.
2. Call issue_dap_reward(user, 'your_reward_key', logger) at the trigger point.

One-time enforcement uses DappPointEvent as a lightweight tracking table —
no extra migration required. The action field is stored as 'dap_reward:<key>'.
"""

import os
import logging
import requests as http_requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reward configuration
# ---------------------------------------------------------------------------

DAP_REWARDS = {
    'welcome_bonus': {
        'amount': 1000,
        'description': 'Welcome bonus',
        'one_time': True,
    },
    'follow_peacelovemusic': {
        'amount': 200,
        'description': 'Followed PeaceLoveMusic',
        'one_time': True,
    },
    'creator_upgrade': {
        'amount': 1000,
        'description': 'Creator upgrade bonus',
        'one_time': True,
    },
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _dap_base():
    return os.environ.get('DAP_SERVICE_URL', '').rstrip('/')

def _dap_headers():
    return {'X-API-Key': os.environ.get('AGENT_API_KEY', '')}


def _dap_register(stacks_address: str) -> bool:
    """Register a Stacks address with the DAP service. Returns True on success."""
    try:
        resp = http_requests.post(
            f"{_dap_base()}/api/users/register",
            json={'stacks_address': stacks_address},
            headers=_dap_headers(),
            timeout=15,
        )
        # 200 = registered now, 409 = already registered — both are fine
        return resp.status_code in (200, 201, 409)
    except Exception as e:
        logger.warning(f"[dap_rewards] register failed for {stacks_address}: {e}")
        return False


def _dap_mint(stacks_address: str, amount: int, description: str) -> bool:
    """Mint DAP credits for a Stacks address. Returns True on success."""
    try:
        resp = http_requests.post(
            f"{_dap_base()}/api/credits/mint",
            json={
                'stacks_address': stacks_address,
                'amount': amount,
                'description': description,
            },
            headers=_dap_headers(),
            timeout=15,
        )
        if resp.status_code in (200, 201):
            return True
        logger.warning(f"[dap_rewards] mint returned {resp.status_code} for {stacks_address}: {resp.text[:200]}")
        return False
    except Exception as e:
        logger.warning(f"[dap_rewards] mint failed for {stacks_address}: {e}")
        return False

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def issue_dap_reward(user, reward_key: str, log=None) -> bool:
    """
    Issue a DAP credit reward to a user.

    - Looks up the reward config in DAP_REWARDS.
    - For one-time rewards, checks DappPointEvent for a prior issuance.
      If already issued, returns False without calling the DAP service.
    - Registers the user with the DAP service (idempotent), then mints.
    - On success, records a DappPointEvent so one-time guards work.
    - All failures are non-fatal: logged and returned as False.

    Returns True if credits were minted, False otherwise.
    """
    _log = log or logger

    reward = DAP_REWARDS.get(reward_key)
    if not reward:
        _log.error(f"[dap_rewards] Unknown reward key: {reward_key}")
        return False

    stacks_address = getattr(user, 'stacks_address', None)
    if not stacks_address:
        _log.warning(f"[dap_rewards] user {user.pk} has no stacks_address — skipping {reward_key}")
        return False

    if not _dap_base():
        _log.warning(f"[dap_rewards] DAP_SERVICE_URL not set — skipping {reward_key}")
        return False

    # One-time check via DappPointEvent
    if reward.get('one_time', True):
        try:
            from .models import DappPointEvent
            tracking_action = f'dap_reward:{reward_key}'
            if DappPointEvent.objects.filter(user=user, action=tracking_action).exists():
                _log.info(f"[dap_rewards] {reward_key} already issued to {user.username} — skipping")
                return False
        except Exception as e:
            _log.warning(f"[dap_rewards] one-time check failed for {reward_key}: {e} — proceeding anyway")

    # Register (idempotent) then mint
    _dap_register(stacks_address)

    amount = reward['amount']
    description = reward['description']
    minted = _dap_mint(stacks_address, amount, description)

    if minted:
        # Record issuance for one-time tracking
        try:
            from .models import DappPointEvent
            DappPointEvent.objects.create(
                user=user,
                action=f'dap_reward:{reward_key}',
                points=amount,
                description=f'DAP credit reward: {description}',
            )
        except Exception as e:
            _log.warning(f"[dap_rewards] failed to record DappPointEvent for {reward_key}: {e}")

        _log.info(f"[dap_rewards] Issued {amount} credits ({reward_key}) to {user.username} ({stacks_address})")
        return True

    return False
