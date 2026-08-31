"""Enterprise app config"""

from django.conf import settings
from prometheus_client import Gauge

from authentik.blueprints.apps import ManagedAppConfig
from authentik.lib.utils.time import fqdn_rand
from authentik.tasks.schedules.common import ScheduleSpec

GAUGE_LICENSE_USAGE = Gauge(
    "authentik_enterprise_license_usage",
    "Enterprise license usage (percentage per user type).",
    ["user_type"],
)
GAUGE_LICENSE_EXPIRY = Gauge(
    "authentik_enterprise_license_expiry_seconds", "Duration until license expires, in seconds."
)


class EnterpriseConfig(ManagedAppConfig):
    """Base app config for all enterprise apps"""


class AuthentikEnterpriseConfig(EnterpriseConfig):
    """Enterprise app config"""

    name = "authentik.enterprise"
    label = "authentik_enterprise"
    verbose_name = "authentik Enterprise"
    default = True

    def enabled(self):
        """Return true if enterprise is enabled and valid"""
        return self.check_enabled() or settings.TEST

    def check_enabled(self):
        """Actual enterprise check, cached"""
        from authentik.enterprise.license import LicenseKey

        return LicenseKey.cached_summary().status.is_valid

    @ManagedAppConfig.reconcile_global
    def warn_dev_license_override(self):
        """Make it obvious in the logs when the development license override is on"""
        from authentik.enterprise.license import dev_license_override_enabled

        if not dev_license_override_enabled():
            return
        self.logger.warning(
            "Enterprise development license override is enabled. Enterprise features are "
            "unlocked for development and testing. "
            "Disable with AUTHENTIK_ENTERPRISE__DEV_LICENSE_OVERRIDE=false.",
        )

    @property
    def tenant_schedule_specs(self) -> list[ScheduleSpec]:
        from authentik.enterprise.tasks import enterprise_update_usage

        return [
            ScheduleSpec(
                actor=enterprise_update_usage,
                crontab=f"{fqdn_rand('enterprise_update_usage')} */2 * * *",
            ),
        ]
