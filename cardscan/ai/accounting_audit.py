"""Offline search-action diagnostics. Does not alter billing estimates or budgets."""
from collections import Counter
from decimal import Decimal
from .costs import usage_cost


def search_action_audit(response):
    """Distinguish processed actions from output attempts; never claim an invoice."""
    conservative = usage_cost(response)
    items = response.get('output', [])
    if not isinstance(items,list) or any(not isinstance(i,dict) for i in items):
        return {'status':'unknown', 'search_action_estimate_usd':None}
    web = [i for i in items if i.get('type')=='web_search_call']
    counts = Counter()
    seen, issues = set(), []
    if conservative is None: issues.append('Missing or invalid token usage')
    model = response.get('model')
    if not isinstance(model,str) or not (model=='gpt-5.4-mini' or model.startswith('gpt-5.4-mini-')):
        issues.append('Unknown model for current rate card')
    for item in web:
        key = item.get('id')
        if not isinstance(key,str) or not key or key in seen:
            issues.append('Missing or duplicate web action ID')
        if isinstance(key,str): seen.add(key)
        action = item.get('action')
        if not isinstance(action,dict):
            issues.append('Malformed web action'); continue
        kind = action.get('type')
        status = item.get('status')
        if not isinstance(kind,str) or not isinstance(status,str):
            issues.append('Invalid web action type/status');continue
        if kind not in {'search','open_page','find_in_page'}:
            issues.append('Unknown web action kind')
        counts[(kind,status)] += 1
        if status not in {'completed','searching','in_progress','failed','incomplete'}:
            issues.append('Unknown web action status')
        if status not in {'completed','searching','in_progress'}:
            issues.append('Failed or incomplete action has uncertain billing')
    search_count = counts[('search','completed')]
    tool_usage = response.get('tool_usage')
    if tool_usage is not None and (not isinstance(tool_usage,dict) or not isinstance(tool_usage.get('web_search',{}),dict)):
        issues.append('Malformed reported tool usage');reported = None
    else:
        reported = (tool_usage or {}).get('web_search',{}).get('num_requests')
    if reported is not None and (type(reported) is not int or reported < 0 or reported != search_count):
        issues.append('Reported search-request counter differs from completed search actions')
    estimate = None
    if conservative is not None and not issues:
        estimate = str(Decimal(conservative['token_cost_usd']) + search_count*Decimal('0.01'))
    return {'status':'review_required' if issues else 'diagnostic_only',
            'web_output_items':len(web), 'completed_actions':sum(n for (k,s),n in counts.items() if s=='completed'),
            'completed_search_actions':search_count,
            'unfinished_actions':sum(n for (k,s),n in counts.items() if s!='completed'),
            'reported_search_requests':reported,
            'conservative_estimate_usd':None if conservative is None else conservative['estimated_total_usd'],
            'search_action_estimate_usd':estimate,'issues':issues,
            'note':'Not an invoice. Published search-action fee plus token estimate; production reserves and original estimator unchanged.'}
