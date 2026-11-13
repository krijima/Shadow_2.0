import os
import sys

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from shadow_lock import ShadowLock

def test_shadow_lock_blocks_unauthorized_purchase():
    lock = ShadowLock()
    task = {"steps_taken": 2, "authorized_goal": "Cancel subscription"}
    
    # Attempting to click an upgrade/purchase button
    action = {
        "action": "click",
        "element_id": "btn-upgrade",
        "element_text": "Upgrade to Platinum for $49.99/mo"
    }
    allowed, reason = lock.validate_action(action, task)
    assert allowed is False
    assert "purchase" in reason.lower() or "price" in reason.lower()

def test_shadow_lock_requires_approval_on_cancel_confirm():
    lock = ShadowLock()
    action = {
        "action": "click",
        "element_id": "btn-confirm-cancel",
        "element_text": "Yes, cancel my subscription"
    }
    needs_approval = lock.requires_approval(action)
    assert needs_approval is True

def test_shadow_lock_max_steps_exceeded():
    lock = ShadowLock()
    task = {"steps_taken": 30, "authorized_goal": "Cancel subscription"}
    action = {
        "action": "click",
        "element_id": "btn-next",
        "element_text": "Next"
    }
    allowed, reason = lock.validate_action(action, task)
    assert allowed is False
    assert "limit" in reason.lower()
