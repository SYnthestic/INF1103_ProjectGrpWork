"""JSON API for audits (under /api): run one, list yours, fetch one."""

from typing import Any

from flask import jsonify, request

from web.routes import Route, RouteGroup


class AuditApi(RouteGroup):
    """Audits for API clients. Every route needs a logged-in user, and users
    only ever see their own audits."""

    name = "audits"
    url_prefix = "/api"

    def routes(self) -> list[Route]:
        return [
            Route("/audits", self.create_audit, ("POST",), login=True),
            Route("/audits", self.list_audits, ("GET",), login=True),
            Route("/audits/<int:audit_id>", self.get_audit, ("GET",), login=True),
        ]

    def not_logged_in(self) -> Any:
        return jsonify(error="login required"), 401

    def create_audit(self) -> Any:
        audit, error, status = self.audit_service.create_audit(
            self.username, request.get_json(silent=True)
        )
        if error:
            return jsonify(error=error), status
        return jsonify(audit=audit), status

    def list_audits(self) -> Any:
        return jsonify(self.data.get_user_audits(self.username))

    def get_audit(self, audit_id: int) -> Any:
        for audit in self.data.get_user_audits(self.username):
            if audit.get("audit_id") == audit_id:
                return jsonify(audit)
        return jsonify(error="audit not found"), 404
