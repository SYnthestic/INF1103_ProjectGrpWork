"""RouteGroup: a set of related routes, registered on the app as one
blueprint."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from flask import Blueprint, current_app, session as flask_session
from functools import wraps
from typing import Any

from web.service import AuditService
from .route import Route


class RouteGroup(ABC):
    """A set of related routes, registered on the app as one blueprint."""

    name: str = ""
    url_prefix: str | None = None
    template_folder: str | None = None

    @abstractmethod
    def routes(self) -> list[Route]:
        """The routes this group answers."""

    @abstractmethod
    def not_logged_in(self) -> Any:
        """The response when a route needs a login and nobody is logged in."""

    def on_register(self, blueprint: Blueprint) -> None:
        """Extra set-up for the blueprint (none by default)."""

    def blueprint(self) -> Blueprint:
        """A new blueprint holding this group's routes. A new one is made for
        each app, so several apps (as in the tests) never share route objects."""
        blueprint = Blueprint(
            self.name,
            type(self).__module__,
            url_prefix=self.url_prefix,
            template_folder=self.template_folder,
        )
        for route in self.routes():
            view = self.login_required(route.view) if route.login else route.view
            blueprint.add_url_rule(
                route.rule,
                endpoint=route.endpoint,
                view_func=view,
                methods=list(route.methods),
            )
        self.on_register(blueprint)
        return blueprint

    def login_required(self, view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def checked(*args: Any, **kwargs: Any) -> Any:
            if self.username is None:
                return self.not_logged_in()
            if self.data.get_user(self.username) is None:
                # The account was deleted (e.g. by an admin) while logged in.
                self.workspaces.discard(self.username)
                self.end_session()
                return self.not_logged_in()
            return view(*args, **kwargs)

        return checked

    # ----- what every route can use -----
    # The managers are read from the running app on each request (not stored
    # here), so the app (or a test) can swap one, e.g. for a fake AI.
    @property
    def ai(self) -> Any:
        return current_app.extensions["ai"]

    @property
    def logic(self) -> Any:
        return current_app.extensions["logic"]

    @property
    def data(self) -> Any:
        return current_app.extensions["data"]

    @property
    def workspaces(self) -> Any:
        return current_app.extensions["workspaces"]

    @property
    def exporter(self) -> Any:
        """A report exporter the app was given (tests use a fake), or None."""
        return current_app.extensions.get("exporter")

    @property
    def audit_service(self) -> AuditService:
        return AuditService(self.ai, self.logic, self.data, current_app.logger)

    @property
    def username(self) -> str | None:
        return flask_session.get("username")

    def start_session(self, username: str) -> None:
        flask_session.clear()
        flask_session["username"] = username
        flask_session["boot"] = current_app.config["BOOT_ID"]

    def end_session(self) -> None:
        flask_session.clear()
