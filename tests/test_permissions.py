from apps.api.app.core.permissions import PERMISSIONS
def test_critical_permissions_present():
 for p in ['tenant.manage','users.manage','accounts.manage','accounts.enable_live','audit.read','system.manage']: assert p in PERMISSIONS
