"""Pocket FM's supplied route, exercised through the real API and approval gate."""
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import main

URL = 'https://pocketfm.com/'


def control(kind, label, enabled=True):
    return {'shadow_id': kind, 'tag': 'button', 'type': 'button', 'text': label,
            'accessible_name': label, 'visible': True, 'enabled': enabled,
            'provider_control': kind, 'in_form': False}


def navigate(client, task, kind, label, text='', enabled=True):
    return client.post('/api/navigate', json={'task_id': task, 'page_snapshot': {
        'url': URL, 'page_text': text, 'elements': [control(kind, label, enabled),
            control('store', 'Store')]}}).json()


@pytest.mark.parametrize('approved', [False, True])
def test_pocket_route_navigates_without_model_then_requires_single_use_approval(monkeypatch, approved):
    monkeypatch.setattr(main.navigator, 'plan_next_action', lambda *args: pytest.fail('Pocket route must not call Gemini'))
    client = TestClient(main.app)
    task = client.post('/api/task', json={'instruction': 'Cancel my Pocket FM subscription',
        'mode': 'observe', 'url': URL}).json()['task_id']
    for kind, label, text in [('profile', 'Profile', 'Home'),
                             ('manage_subscriptions', 'Manage Subscriptions', 'Profile menu'),
                             ('active_plan', '60 mins daily', 'Active subscriptions Premium Renews monthly')]:
        data = navigate(client, task, kind, label, text)
        assert data['action']['element_id'] == kind
        assert data['action']['action'] == 'click'
        assert data['reversible'] is True
        assert data['requires_approval'] is False
    data = navigate(client, task, 'cancel_subscription', 'Cancel Subscription', 'Current plan details Status Active')
    assert data['requires_approval'] is True
    assert data['action']['element_id'] == 'cancel_subscription'
    assert client.get(f'/api/task/{task}').json()['status'] == 'paused'
    approval = data['approval_id']
    result = client.post(f'/api/approve/{approval}', json={'approved': approved})
    assert result.status_code == 200
    assert result.json()['status'] == ('approved' if approved else 'rejected')
    assert client.post(f'/api/approve/{approval}', json={'approved': True}).status_code == 409


def test_disabled_pocket_cancel_is_not_approved_or_falsely_completed():
    client = TestClient(main.app)
    task = client.post('/api/task', json={'instruction': 'Cancel my Pocket FM subscription',
        'mode': 'observe', 'url': URL}).json()['task_id']
    data = navigate(client, task, 'cancel_subscription', 'Cancel Subscription',
                    'Current plan details Amount ₹0 Status Active', enabled=False)
    assert data['requires_approval'] is False
    assert data['status'] == 'paused'
    assert data['action']['action'] == 'highlight'
    assert data['waiting_for_user'] is True
    assert 'disabled' in data['guidance'].lower()


def test_pocket_faq_does_not_claim_completed_cancellation():
    from pocketfm_route import match_pocketfm
    step = match_pocketfm({'url': URL, 'page_text':
        'What happens when my subscription is cancelled? How do I cancel Pocket Premium?',
        'elements': [control('cancel_subscription', 'Cancel Subscription')]})
    assert step.get('completed') is not True
    assert step['final'] is True
