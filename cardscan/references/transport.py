"""Bounded read-only JSON transport. No full-page storage, credentials or retries."""
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class SourceRetrievalError(ValueError):
    pass


def canonical_source_url(url):
    p = urlsplit(url)
    if (p.scheme != 'https' or not p.hostname or p.username or p.password
            or p.port not in (None, 443) or p.query or p.fragment):
        raise ValueError('Plain HTTPS source URL required; no credentials, query or fragment')
    return 'https://' + p.hostname.lower() + p.path.rstrip('/')


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise SourceRetrievalError('Source redirect refused; explicit source review required')


@dataclass(frozen=True)
class SourceDocument:
    url: str
    retrieved_at: str
    sha256: str
    data: dict


class JsonTransport:
    """Only the documented TCGdex single-card endpoint is enabled by default."""
    def __init__(self, *, timeout=20, max_bytes=1_000_000, opener=None):
        if not 1 <= timeout <= 30 or not 1 <= max_bytes <= 1_000_000:
            raise ValueError('Bounded timeout and response size required')
        self.timeout, self.max_bytes = timeout, max_bytes
        self.opener = opener or build_opener(NoRedirects())

    def get(self, url):
        url = canonical_source_url(url)
        p = urlsplit(url)
        if p.hostname != 'api.tcgdex.net' or not re.fullmatch(r'/v2/(?:en|ja|fr|de|es|it|pt)/cards/[A-Za-z0-9.-]+', p.path):
            raise SourceRetrievalError('Endpoint is not approved for source retrieval')
        try:
            req = Request(url, headers={'User-Agent':'CardScanSourceVerifier/1.0', 'Accept':'application/json'})
            with self.opener.open(req, timeout=self.timeout) as response:
                if response.status != 200 or canonical_source_url(response.geturl()) != url:
                    raise SourceRetrievalError('Source did not return the approved URL with HTTP 200')
                if response.headers.get_content_type() != 'application/json':
                    raise SourceRetrievalError('Source is not JSON; no HTML/challenge processing')
                body = response.read(self.max_bytes + 1)
                if len(body) > self.max_bytes:
                    raise SourceRetrievalError('Source response exceeds size limit')
            def no_duplicate_keys(pairs):
                result = {}
                for key, value in pairs:
                    if key in result: raise ValueError('Duplicate source JSON key')
                    result[key] = value
                return result
            data = json.loads(body, object_pairs_hook=no_duplicate_keys,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite JSON number')))
            if not isinstance(data, dict): raise ValueError('Source JSON must be an object')
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            # Do not expose response bodies, URLs containing credentials or key values.
            raise SourceRetrievalError(f'Source retrieval failed: {type(exc).__name__}') from exc
        return SourceDocument(url, datetime.now(timezone.utc).isoformat(), sha256(body).hexdigest(), data)
