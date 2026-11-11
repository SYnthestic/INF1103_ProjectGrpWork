"""The base for every group of web routes.

Class overview
    Route        one URL: its path, the method that answers it, the HTTP
                 methods it accepts and whether it needs a logged-in user
    RouteGroup   abstract: a set of related routes. Subclasses (PageRoutes,
                 AuthApi, AuditApi) list their routes and say what happens when
                 nobody is logged in; the base turns them into a Flask
                 blueprint (template method) and gives every route the same
                 access to the managers and the logged-in user.

The app treats every group the same way (polymorphism): it asks each one for
its blueprint and registers it, without knowing which kind it is.
"""

from .route import Route
from .route_group import RouteGroup

__all__ = [
    "Route",
    "RouteGroup",
]
