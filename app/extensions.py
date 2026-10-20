"""
Central extensions registry.

Instantiates extensions in a decoupled state to prevent circular imports across
models, blueprints, tasks, and services.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, AnonymousUserMixin
from flask_wtf.csrf import CSRFProtect


class AnonymousUser(AnonymousUserMixin):
    def __bool__(self) -> bool:
        return False


db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.anonymous_user = AnonymousUser
csrf = CSRFProtect()

login_manager.login_view = "auth.login"
login_manager.login_message = "Please sign in to continue."
login_manager.login_message_category = "warning"


@login_manager.user_loader
def load_user(user_id: str):
    from app.blueprints.auth.models import User
    try:
        user = db.session.get(User, int(user_id))
        if user is not None and not user.is_active:
            return None  # deactivated by an admin: invalidate existing sessions / remember cookies
        return user
    except (ValueError, TypeError):
        return None
