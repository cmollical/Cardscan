"""Diagnostic failure handling with synthetic HTTP responses; no live CI calls."""
import io
import json
import unittest
from urllib.error import HTTPError
from unittest.mock import MagicMock
from cardscan.tcgplayer_probe import probe, SALES_URL


class TCGplayerProbeTests(unittest.TestCase):
    def test_forbidden_stops_once_without_credentials_or_validation_tokens(self):
        opener = MagicMock(side_effect=HTTPError(SALES_URL, 403, 'Forbidden', {}, io.BytesIO(b'Forbidden')))
        result = probe(opener)
        self.assertEqual(result['status'], 'access_denied')
        self.assertFalse(result['live_sales_retrieved'])
        self.assertEqual(opener.call_count, 1)
        request = opener.call_args.args[0]
        self.assertNotIn('?', request.full_url)
        self.assertNotIn('Cookie', request.headers)
        self.assertNotIn('Authorization', request.headers)
        self.assertEqual(json.loads(request.data)['limit'], 5)
        self.assertNotIn('offset', json.loads(request.data))

    def response(self, content_type, body):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.headers = {'Content-Type': content_type}
        response.read.return_value = body
        return MagicMock(return_value=response)

    def test_html_challenge_is_not_sales(self):
        result = probe(self.response('text/html', b'<html>challenge</html>'))
        self.assertEqual(result['status'], 'invalid_response')
        self.assertFalse(result['live_sales_retrieved'])

    def test_unknown_json_schema_is_not_sales(self):
        result = probe(self.response('application/json', b'{"error":"login required"}'))
        self.assertEqual(result['status'], 'schema_review_required')
        self.assertFalse(result['live_sales_retrieved'])

    def test_future_success_does_not_invent_a_valuation(self):
        result = probe(self.response('application/json', b'{"data":[]}'))
        self.assertEqual(result['status'], 'response_available_for_schema_review')
        self.assertIsNone(result['valuation'])
