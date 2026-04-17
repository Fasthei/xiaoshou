"""
Shared role constants — mirrors docs/ROLES.md.

This module is intended to be copied verbatim into ticket / opscenter / cloudmgmt
systems (or published as an internal pip package) so every service judges roles
against the same codes.
"""

ADMIN = "admin"

# Sales org
SALES = "sales"
SALES_MANAGER = "sales_manager"

# Cross-functional
FINANCE = "finance"
SUPPORT = "support"
AUDITOR = "auditor"
READONLY = "readonly"

ALL_ROLES = {
    ADMIN, SALES, SALES_MANAGER,
    FINANCE, SUPPORT, AUDITOR, READONLY,
}

# Convenience groups
WRITE_ROLES = {ADMIN, SALES, SALES_MANAGER}
READ_ROLES = ALL_ROLES  # 所有角色都至少能读
MANAGER_ROLES = {ADMIN, SALES_MANAGER}
