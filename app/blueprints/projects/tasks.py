"""
Background event tasks for projects and issues.
"""
from __future__ import annotations

import logging
from app.core.celery_app import celery

logger = logging.getLogger("opencampus.tasks.projects")

if celery is not None:
    @celery.task(name="projects.on_issue_created")
    def on_issue_created_task(project_id: int, issue_id: int, title: str, created_by: int):
        from app.blueprints.notifications.tasks import create_in_app_notification_task
        from app.blueprints.projects.models import ProjectMember, Project

        project = Project.query.get(project_id)
        if not project:
            return
        members = ProjectMember.query.filter_by(project_id=project_id).all()
        for m in members:
            if m.user_id != created_by:
                create_in_app_notification_task(
                    m.user_id,
                    "issue_created",
                    f"New issue on {project.name}: {title}",
                    f"/projects/issue/{issue_id}",
                )

    @celery.task(name="projects.on_mentorship_requested")
    def on_mentorship_requested_task(request_id: int, project_id: int, student_id: int):
        from app.blueprints.notifications.tasks import create_in_app_notification_task
        from app.blueprints.projects.models import ProjectMember, Project
        from app.blueprints.auth.models import User

        project = Project.query.get(project_id)
        student = User.query.get(student_id)
        if not project or not student:
            return

        owners = ProjectMember.query.filter_by(project_id=project_id, role="owner").all()
        for owner in owners:
            create_in_app_notification_task(
                owner.user_id,
                "mentorship_requested",
                f"{student.full_name} requested mentorship on {project.name}",
                f"/mentorship/",
            )
else:
    def on_issue_created_task(project_id: int, issue_id: int, title: str, created_by: int):
        pass

    def on_mentorship_requested_task(request_id: int, project_id: int, student_id: int):
        pass
