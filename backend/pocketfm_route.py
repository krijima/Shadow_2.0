"""Pocket FM route supplied by the user; every target comes from the live DOM."""
import re
from urllib.parse import urlparse


def is_pocketfm(url):
    host = (urlparse(url).hostname or '').lower()
    return host == 'pocketfm.com' or host.endswith('.pocketfm.com')


LABELS = {
    'profile': r'profile',
    'manage_subscriptions': r'manage subscriptions',
    'active_plan': r'\d+\s*mins?(?:\s+daily)?(?:\s+premium.*)?',
    'cancel_subscription': r'cancel subscription',
    'confirm_cancel': r'(?:confirm cancellation|confirm cancel|yes,? cancel(?: subscription)?|cancel subscription)',
}


def match_pocketfm(snapshot):
    text = str(snapshot.get('page_text') or '')
    elements = snapshot.get('elements', [])
    base = {'provider': 'pocketfm', 'help_url': 'https://pocketfm.com/', 'source': 'user_supplied_flow'}
    # A cancellation FAQ is not proof that this account was cancelled. Require
    # a standalone success/status line in the observed active panel.
    if re.search(r'^\s*(?:your )?(?:subscription (?:has been |is )?cancelled|cancellation (?:is )?(?:confirmed|successful))[.!]?\s*$', text, re.I | re.M):
        return {**base, 'route_step': 'complete', 'completed': True}
    for kind in ('confirm_cancel', 'cancel_subscription', 'active_plan', 'manage_subscriptions', 'profile'):
        for element in elements:
            label = ' '.join(str(element.get('accessible_name') or element.get('text') or '').split())
            if (element.get('provider_control') != kind or not element.get('visible', True)
                    or not re.fullmatch(LABELS[kind], label, re.I)):
                continue
            if kind == 'active_plan' and not re.search(r'active subscriptions', text, re.I):
                continue
            if kind in ('cancel_subscription', 'confirm_cancel') and not re.search(
                    r'current plan|subscription|cancel', text, re.I):
                continue
            if not element.get('enabled', True):
                return {**base, 'route_step': 'unavailable', 'pause_reason':
                        'Pocket FM has disabled Cancel Subscription for this plan. No cancellation was made.'}
            return {**base, 'route_step': kind, 'reversible': kind in (
                'profile', 'manage_subscriptions', 'active_plan'),
                'final': kind in ('cancel_subscription', 'confirm_cancel'),
                'action': {'action': 'click', 'element_id': element['shadow_id'], 'value': '',
                           'reason': f'Pocket FM: {label}', 'confidence': 1.0}}
    return {**base, 'route_step': 'unavailable', 'pause_reason':
            'SHADOW could not locate the next Pocket FM control on this page. Refresh Pocket FM and activate SHADOW again.'}
