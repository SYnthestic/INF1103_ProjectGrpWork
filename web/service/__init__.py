"""What the web pages and the JSON API share: account rules, checking an
application, and running one audit through the managers.

Class overview
    AccountRules           the terminal's username and password rules
    ApplicationValidator   the terminal's limits for an application's fields
    AuditService           validate -> AI Manager -> Logic Manager -> Data
                           Manager for one application. It is handed the
                           managers (aggregation) and owns its validator
                           (composition).

Nothing here decides a grant; that is the Logic Manager's job.
"""

from .account_rules import AccountRules
from .application_validator import ApplicationValidator
from .audit_service import AuditService

__all__ = [
    "AccountRules",
    "ApplicationValidator",
    "AuditService",
]
