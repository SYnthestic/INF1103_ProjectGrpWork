"""AdminRoutes: the admin console of the web version (under /admin): manage
accounts and the grant rule thresholds, as the terminal's menu option 11."""

from collections.abc import Callable
from functools import wraps
from typing import Any

from flask import Blueprint, flash, redirect, render_template, request, url_for

from web.routes import Route, RouteGroup
from web.service import AdminService


class AdminRoutes(RouteGroup):
    """Admin-only pages. Every request checks again that the user is still an
    admin, so a demoted or deleted admin loses access at once."""

    name = "admin"
    url_prefix = "/admin"
    template_folder = "templates"

    def routes(self) -> list[Route]:
        post = ("POST",)
        return [
            Route("", self.console, ("GET",), login=True),
            Route("/users", self.create_user, post, login=True),
            Route("/users/<username>/password", self.reset_password, post, login=True),
            Route("/users/<username>/role", self.change_role, post, login=True),
            Route("/users/<username>/delete", self.delete_user, post, login=True),
            Route("/thresholds", self.save_thresholds, post, login=True),
            Route("/thresholds/reset", self.reset_thresholds, post, login=True),
        ]

    def not_logged_in(self) -> Any:
        flash("Please log in first.")
        return redirect(url_for("pages.login"))

    def login_required(self, view: Callable[..., Any]) -> Callable[..., Any]:
        """Logged in (checked by the base class) and an admin (checked here)."""
        logged_in_view = super().login_required(view)

        @wraps(view)
        def admin_only(*args: Any, **kwargs: Any) -> Any:
            if self.username is not None and not self.service.is_admin(self.username):
                return render_template("forbidden.html"), 403
            return logged_in_view(*args, **kwargs)

        return admin_only

    def on_register(self, blueprint: Blueprint) -> None:
        """Every page can ask whether to show the Admin link in the menu."""
        blueprint.app_context_processor(
            lambda: {"is_admin": self.service.is_admin(self.username)}
        )

    @property
    def service(self) -> AdminService:
        return AdminService(self.logic, self.data, self.username or "")

    def back(self, ok: bool, message: Any, anchor: str = "") -> Any:
        for text in message if isinstance(message, list) else [message]:
            flash(("" if ok else "Not changed: ") + text)
        return redirect(url_for("admin.console") + anchor)

    # ----- pages -----
    def console(self) -> Any:
        self.audit_service.use_saved_rules()  # show the thresholds in force
        service = self.service
        users = service.users()
        if users is None:
            flash("The accounts file could not be read.")
        return render_template(
            "admin.html",
            users=users or [],
            roles=self.logic.access.ROLES,
            main_admin=self.logic.access.bootstrap_admin,
            thresholds=service.threshold_rows(),
        )

    def create_user(self) -> Any:
        ok, message = self.service.create_user(
            request.form.get("username", ""),
            request.form.get("password", ""),
            request.form.get("role", ""),
        )
        return self.back(ok, message, "#users")

    def reset_password(self, username: str) -> Any:
        ok, message = self.service.reset_password(username, request.form.get("password", ""))
        return self.back(ok, message, "#users")

    def change_role(self, username: str) -> Any:
        ok, message = self.service.change_role(username, request.form.get("role", ""))
        return self.back(ok, message, "#users")

    def delete_user(self, username: str) -> Any:
        ok, message = self.service.delete_user(username, request.form.get("confirm", ""))
        if ok:
            self.workspaces.discard(username)  # their records in memory go too
        return self.back(ok, message, "#users")

    def save_thresholds(self) -> Any:
        self.audit_service.use_saved_rules()
        ok, message = self.service.save_thresholds(request.form)
        return self.back(ok, message, "#thresholds")

    def reset_thresholds(self) -> Any:
        ok, message = self.service.reset_thresholds()
        return self.back(ok, message, "#thresholds")
