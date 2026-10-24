"""Published standard USD rates checked 2026-10-24; estimates, not invoices."""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Settings:
    model: str = 'gpt-5.4-mini'
    max_search_calls: int = 2
    max_output_tokens: int = 3000
    timeout_seconds: float = 90
    cache_ttl_seconds: int = 3600
    per_request_limit_usd: str = '0.35'
    daily_limit_usd: str = '2.00'
    max_daily_requests: int = 10
    minimum_sales: int = 3
    max_age_days: int = 90

    def __post_init__(self):
        if self.model != 'gpt-5.4-mini':
            raise ValueError('Only the documented gpt-5.4-mini rate card is currently supported')
        for key, low, high in [('max_search_calls', 1, 5), ('max_output_tokens', 512, 10000),
                               ('cache_ttl_seconds', 0, 86400), ('max_daily_requests', 1, 100),
                               ('minimum_sales', 3, 100), ('max_age_days', 0, 365)]:
            value = getattr(self, key)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f'Invalid {key}')
        if not 1 <= self.timeout_seconds <= 300:
            raise ValueError('Invalid timeout')
        for key in ('per_request_limit_usd', 'daily_limit_usd'):
            value = Decimal(getattr(self, key))
            if not value.is_finite() or value <= 0:
                raise ValueError(f'Invalid {key}')

    def reservation(self):
        # Search content size is not a guaranteed numeric cap. Reserve the entire
        # documented model context at uncached rates, plus max output and tools.
        return (Decimal('400000') * Decimal('0.75') / 1_000_000
                + Decimal(self.max_output_tokens) * Decimal('4.50') / 1_000_000
                + Decimal(self.max_search_calls) * Decimal('0.01'))


def usage_cost(response):
    usage = response.get('usage')
    if not isinstance(usage, dict):
        return None
    inputs, outputs = usage.get('input_tokens'), usage.get('output_tokens')
    input_details = usage.get('input_tokens_details') or {}
    output_details = usage.get('output_tokens_details') or {}
    output = response.get('output', [])
    if not isinstance(input_details, dict) or not isinstance(output_details, dict) or not isinstance(output, list) or any(not isinstance(item, dict) for item in output):
        return None
    cached = input_details.get('cached_tokens', 0)
    reasoning = output_details.get('reasoning_tokens', 0)
    if any(type(v) is not int or v < 0 for v in (inputs, outputs, cached, reasoning)) or cached > inputs or reasoning > outputs:
        return None
    calls = sum(item.get('type') == 'web_search_call' for item in output)
    token_cost = ((inputs-cached)*Decimal('0.75') + cached*Decimal('0.075') + outputs*Decimal('4.50'))/1_000_000
    tool_cost = Decimal(calls)*Decimal('0.01')
    return dict(input_tokens=inputs, cached_input_tokens=cached, output_tokens=outputs,
                reasoning_tokens=reasoning, search_calls=calls, token_cost_usd=str(token_cost),
                search_cost_usd=str(tool_cost), estimated_total_usd=str(token_cost+tool_cost),
                rate_date='2026-10-24', model='gpt-5.4-mini',
                billing_note='Search content assumed included in reported input usage; all web-search output items charged conservatively. Reconcile with invoice.')
