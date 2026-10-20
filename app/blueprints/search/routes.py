from __future__ import annotations

from flask import Blueprint, render_template, request

from app.blueprints.search import service
from app.core.rate_limit import limiter

bp = Blueprint("search", __name__, url_prefix="/search")


@bp.route("/")
@limiter.limit("30 per minute")
def index():
    query = request.args.get("q", "").strip()
    results = service.unified_search(query) if query else {"projects": [], "issues": [], "docs": [], "clubs": []}
    return render_template("search/index.html", query=query, results=results)
