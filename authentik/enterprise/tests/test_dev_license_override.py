"""Enterprise development license override tests"""

from django.core.cache import cache
from django.test import TestCase

from authentik.core.models import User
from authentik.core.tests.utils import create_test_admin_user
from authentik.enterprise.license import (
    CACHE_KEY_ENTERPRISE_LICENSE,
    DEV_OVERRIDE_USERS,
    LicenseFlags,
    LicenseKey,
    dev_license_override_enabled,
)
from authentik.enterprise.models import LicenseUsage, LicenseUsageStatus
from authentik.lib.config import CONFIG

OVERRIDE_KEY = "enterprise.dev_license_override"


class TestDevLicenseOverride(TestCase):
    """Development license override tests"""

    def setUp(self):
        # The summary cache is process-wide; make sure no other test's summary leaks in
        cache.delete(CACHE_KEY_ENTERPRISE_LICENSE)

    def test_disabled_by_default(self):
        """Override must be off unless explicitly enabled"""
        self.assertFalse(dev_license_override_enabled())

    @CONFIG.patch(OVERRIDE_KEY, False)
    def test_disabled_unlicensed(self):
        """Without the override, an install with no license stays unlicensed"""
        self.assertEqual(LicenseKey.get_total().status(), LicenseUsageStatus.UNLICENSED)
        self.assertFalse(LicenseKey.cached_summary().status.is_valid)

    @CONFIG.patch(OVERRIDE_KEY, True)
    def test_enabled_reports_valid(self):
        """With the override, an install with no license reports a valid license"""
        total = LicenseKey.get_total()
        self.assertEqual(total.status(), LicenseUsageStatus.VALID)
        self.assertTrue(total.status().is_valid)
        self.assertEqual(total.internal_users, DEV_OVERRIDE_USERS)
        self.assertEqual(total.external_users, DEV_OVERRIDE_USERS)
        self.assertIn(LicenseFlags.NON_PRODUCTION, total.license_flags)

    @CONFIG.patch(OVERRIDE_KEY, True)
    def test_enabled_summary_valid(self):
        """The cached summary reports valid while the override is on"""
        summary = LicenseKey.cached_summary()
        self.assertEqual(summary.status, LicenseUsageStatus.VALID)
        self.assertTrue(summary.status.is_valid)
        self.assertEqual(summary.internal_users, DEV_OVERRIDE_USERS)

    def test_summary_not_cached(self):
        """Turning the override off takes effect immediately, without a stale cache hit"""
        with CONFIG.patch(OVERRIDE_KEY, True):
            self.assertTrue(LicenseKey.cached_summary().status.is_valid)
        with CONFIG.patch(OVERRIDE_KEY, False):
            self.assertFalse(LicenseKey.cached_summary().status.is_valid)

    @CONFIG.patch(OVERRIDE_KEY, True)
    def test_user_count_does_not_exceed(self):
        """Existing users never push the override into a limit-exceeded state"""
        create_test_admin_user()
        self.assertGreater(User.objects.all().count(), 0)
        self.assertEqual(LicenseKey.get_total().status(), LicenseUsageStatus.VALID)

    def test_summary_never_cached(self):
        """An overridden summary is never persisted to the shared cache

        Regression test: /enterprise/license/summary/?cached=false calls summary()
        directly, which would otherwise leave a synthetic "valid" entry in the cache
        that outlives the override being turned off.
        """
        with CONFIG.patch(OVERRIDE_KEY, True):
            LicenseKey.get_total().summary()
            self.assertIsNone(cache.get(CACHE_KEY_ENTERPRISE_LICENSE))
        with CONFIG.patch(OVERRIDE_KEY, False):
            self.assertFalse(LicenseKey.cached_summary().status.is_valid)

    def test_no_usage_records_written(self):
        """The override must not write synthetic license usage history

        Usage records feed _last_valid_date(), which the grace-period thresholds are
        measured from, so fake "valid" rows would mask a real over-seat condition
        after an actual license is installed.
        """
        LicenseUsage.objects.all().delete()
        with CONFIG.patch(OVERRIDE_KEY, True):
            self.assertIsNone(LicenseKey.get_total().record_usage())
        self.assertEqual(LicenseUsage.objects.count(), 0)
