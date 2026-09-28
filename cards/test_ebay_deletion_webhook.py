import hashlib
import json
import os
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from cards.models import Card, MarketListing, MarketSource, PriceHistory
from cards.services.demo_data import seed_demo_data
from cards.views import EBAY_DELETION_ENDPOINT


class EbayAccountDeletionWebhookTests(TestCase):
    verification_token = 'mock-verification-token'
    challenge_code = 'mock-challenge-code'

    def get_challenge(self, environment=None):
        configured_environment = (
            {'EBAY_DELETION_VERIFICATION_TOKEN': self.verification_token}
            if environment is None
            else environment
        )
        with patch.dict(os.environ, configured_environment, clear=True):
            return self.client.get(
                reverse('ebay-account-deletion'),
                {'challenge_code': self.challenge_code},
            )

    def test_get_returns_exact_challenge_response(self):
        response = self.get_challenge()
        expected = hashlib.sha256(
            (
                self.challenge_code
                + self.verification_token
                + 'https://pokemon-card-market.onrender.com/ebay/account-deletion/'
            ).encode('utf-8')
        ).hexdigest()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'application/json')
        self.assertEqual(response.json(), {'challengeResponse': expected})
        self.assertEqual(EBAY_DELETION_ENDPOINT, (
            'https://pokemon-card-market.onrender.com/ebay/account-deletion/'
        ))
        self.assertNotIn(self.verification_token, response.content.decode())
        self.assertNotIn(self.challenge_code, response.content.decode())

    def test_get_without_challenge_code_returns_safe_error(self):
        with patch.dict(
            os.environ,
            {'EBAY_DELETION_VERIFICATION_TOKEN': self.verification_token},
            clear=True,
        ):
            response = self.client.get(reverse('ebay-account-deletion'))

        self.assertEqual(response.status_code, 400)
        self.assertNotIn(self.verification_token, response.content.decode())

    def test_get_without_verification_token_returns_safe_error(self):
        response = self.get_challenge(environment={})

        self.assertEqual(response.status_code, 503)
        self.assertNotIn(self.challenge_code, response.content.decode())

    def test_valid_deletion_notification_is_acknowledged_without_db_changes(self):
        seed_demo_data()
        counts_before = (
            Card.objects.count(),
            MarketSource.objects.count(),
            MarketListing.objects.count(),
            PriceHistory.objects.count(),
        )
        sensitive_values = ('private-username', 'private-user-id', 'private-eias-token')
        payload = {
            'metadata': {'topic': 'MARKETPLACE_ACCOUNT_DELETION'},
            'notification': {
                'username': sensitive_values[0],
                'userId': sensitive_values[1],
                'eiasToken': sensitive_values[2],
            },
        }

        response = self.client.post(
            reverse('ebay-account-deletion'),
            data=json.dumps(payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b'')
        self.assertEqual(
            (
                Card.objects.count(),
                MarketSource.objects.count(),
                MarketListing.objects.count(),
                PriceHistory.objects.count(),
            ),
            counts_before,
        )
        for sensitive_value in sensitive_values:
            self.assertNotIn(sensitive_value, response.content.decode())

    def test_post_does_not_require_csrf_token(self):
        csrf_client = self.client_class(enforce_csrf_checks=True)

        response = csrf_client.post(
            reverse('ebay-account-deletion'),
            data=json.dumps({'metadata': {'topic': 'MARKETPLACE_ACCOUNT_DELETION'}}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 204)

    def test_invalid_json_returns_400(self):
        response = self.client.post(
            reverse('ebay-account-deletion'),
            data='{invalid',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)

    def test_unexpected_topic_returns_400(self):
        response = self.client.post(
            reverse('ebay-account-deletion'),
            data=json.dumps({'metadata': {'topic': 'OTHER_TOPIC'}}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)

    def test_other_methods_return_405(self):
        url = reverse('ebay-account-deletion')

        self.assertEqual(self.client.put(url, data=b'{}').status_code, 405)
        self.assertEqual(self.client.delete(url).status_code, 405)
