"""
Populate the database with realistic demo data so the platform can be
explored immediately after setup.

Usage:
    python scripts/seed_data.py            # adds demo data (safe to skip if already seeded)
    python scripts/seed_data.py --reset     # wipes the database file first, then seeds

Every login below uses the password: password123
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app
from app.core import db
from app.blueprints.auth import service as auth_service
from app.blueprints.clubs import service as clubs_service
from app.blueprints.projects import service as projects_service
from app.blueprints.issues import service as issues_service
from app.blueprints.docs import service as docs_service
from app.blueprints.mentorship import service as mentorship_service
from app.blueprints.announcements import service as announcements_service

DEMO_PASSWORD = "password123"


def seed(app) -> None:
    with app.app_context():
        if db.query_one("SELECT id FROM users LIMIT 1"):
            print("Database already has data -- skipping seed. Use --reset to start fresh.")
            return

        print("Creating users...")
        _register = auth_service.register_user

        def register(email, password, full_name, role="student"):
            """Register a demo user and mark them verified so the advertised
            demo logins work without an email round-trip."""
            user = _register(email, password, full_name, role)
            db.execute("UPDATE users SET is_verified = 1, verification_token = '' WHERE id = ?", (user["id"],))
            return user

        admin = register("admin@opencampus.dev", DEMO_PASSWORD, "Priya Nair", "student")
        db.execute("UPDATE users SET role = 'platform_admin' WHERE id = ?", (admin["id"],))

        maintainer1 = register("arjun.k@opencampus.dev", DEMO_PASSWORD, "Arjun Kumar", "student")
        db.execute("UPDATE users SET role = 'club_admin' WHERE id = ?", (maintainer1["id"],))

        maintainer2 = register("sara.j@opencampus.dev", DEMO_PASSWORD, "Sara Jacob", "student")
        db.execute("UPDATE users SET role = 'club_admin' WHERE id = ?", (maintainer2["id"],))

        mentor1 = register("mentor.das@opencampus.dev", DEMO_PASSWORD, "Dr. Ravi Das", "mentor")
        student1 = register("student.meera@opencampus.dev", DEMO_PASSWORD, "Meera Pillai", "student")
        student2 = register("student.karthik@opencampus.dev", DEMO_PASSWORD, "Karthik Rao", "student")

        print("Creating clubs...")
        cs_club = clubs_service.create_club(
            "Computer Science Society", "Building tools and running workshops for the CS department.", maintainer1["id"]
        )
        clubs_service.set_club_admin(cs_club["id"], maintainer1["id"])
        clubs_service.set_club_secret_code(cs_club["id"], "cs_secret_123")

        robotics_club = clubs_service.create_club(
            "Robotics Club", "Hardware and software projects for autonomous systems.", maintainer2["id"]
        )
        clubs_service.set_club_admin(robotics_club["id"], maintainer2["id"])
        clubs_service.set_club_secret_code(robotics_club["id"], "robotics_secret_123")

        clubs_service.join_club(cs_club["id"], student1["id"])
        clubs_service.join_club(cs_club["id"], student2["id"])
        clubs_service.join_club(robotics_club["id"], student1["id"])

        print("Creating projects...")
        campus_connect = projects_service.create_project(
            cs_club["id"], "CampusConnect",
            "A directory app connecting students with clubs, events, and study groups.",
            "Python, Flask, SQLite", "", "beginner", maintainer1["id"],
        )
        grade_tracker = projects_service.create_project(
            cs_club["id"], "GradeTracker CLI",
            "A command-line tool for students to log and visualize their semester grades.",
            "Python, Click, Matplotlib", "", "intermediate", maintainer1["id"],
        )
        line_follower = projects_service.create_project(
            robotics_club["id"], "Line Follower Firmware",
            "Firmware for a line-following robot used in the annual robotics workshop.",
            "C++, PlatformIO, Arduino", "", "advanced", maintainer2["id"],
        )
        projects_service.update_status(line_follower["id"], "seeking_maintainer")

        # Extra projects so every filter option has at least one visible result
        club_portal = projects_service.create_project(
            cs_club["id"], "Club Portal",
            "Self-service portal for club admins to manage members and announce events. Ready for new contributors.",
            "React, FastAPI, SQLite", "", "beginner", maintainer2["id"],
            is_seeking_contributors=True, required_skills="React, CSS",
        )
        design_system = projects_service.create_project(
            cs_club["id"], "Design System",
            "Shared UI component library used across all CS Society web projects.",
            "Figma, Storybook, TypeScript", "", "intermediate", maintainer1["id"],
            is_seeking_contributors=True, required_skills="TypeScript, Storybook",
        )
        drone_nav = projects_service.create_project(
            robotics_club["id"], "Drone Navigation Stack",
            "Autonomous navigation firmware for the hexacopter drone used in research demos.",
            "C++, ROS 2, Python", "", "advanced", maintainer2["id"],
            is_seeking_contributors=True, required_skills="ROS 2, C++",
        )
        # Mark some with non-active statuses so the status filter is exercisable
        legacy_notes = projects_service.create_project(
            cs_club["id"], "Lecture Notes Archive",
            "Static site that archives lecture notes from previous semesters. In maintenance-only mode.",
            "Hugo, Markdown", "", "beginner", maintainer1["id"],
        )
        projects_service.update_status(legacy_notes["id"], "maintenance")

        projects_service.join_as_contributor(campus_connect["id"], student1["id"])
        projects_service.join_as_contributor(grade_tracker["id"], student2["id"])
        projects_service.join_as_contributor(club_portal["id"], student1["id"])
        projects_service.join_as_contributor(drone_nav["id"], student2["id"])

        print("Creating issues...")
        issue1 = issues_service.create_issue(
            campus_connect["id"], "Add search bar to club directory",
            "Users should be able to filter clubs by name or category on the directory page.",
            "beginner", maintainer1["id"],
        )
        issue2 = issues_service.create_issue(
            campus_connect["id"], "Fix broken pagination on events page",
            "Clicking 'next page' on /events resets the filter selections.",
            "intermediate", maintainer1["id"],
        )
        issue3 = issues_service.create_issue(
            grade_tracker["id"], "Add GPA trend chart",
            "Plot cumulative GPA over semesters using matplotlib.",
            "intermediate", maintainer1["id"],
        )
        issue4 = issues_service.create_issue(
            line_follower["id"], "Calibrate IR sensor thresholds",
            "Current thresholds misfire under fluorescent lighting.",
            "advanced", maintainer2["id"],
        )
        issues_service.claim_issue(issue1["id"], student1["id"])
        issues_service.add_comment(issue1["id"], student1["id"], "Started on this -- planning to use a simple LIKE query first.")
        issues_service.add_comment(issue1["id"], maintainer1["id"], "Sounds good, ping me if you want it debounced client-side too.")
        issues_service.update_status(issue2["id"], "in_review", maintainer1["id"])
        issues_service.claim_issue(issue3["id"], student2["id"])
        issues_service.update_status(issue3["id"], "done", maintainer1["id"])

        print("Publishing documentation...")
        docs_service.create_document(
            campus_connect["id"], "README",
            "CampusConnect helps students discover clubs and events.\n\n"
            "## Setup\n1. Clone the repo\n2. pip install -r requirements.txt\n3. python run.py\n\n"
            "## Contributing\nCheck the open issues board and comment to claim one.",
            "readme", maintainer1["id"],
        )
        docs_service.create_document(
            campus_connect["id"], "Onboarding Guide",
            "New to the project? Start here.\n\n"
            "1. Read the README\n2. Set up your local environment\n3. Pick a 'beginner' issue\n"
            "4. Comment on the issue before starting so we don't duplicate work.",
            "onboarding", maintainer1["id"],
        )
        docs_service.create_document(
            line_follower["id"], "Architecture Overview",
            "The firmware is split into three modules: sensor input, PID control loop, and motor output.\n"
            "See /src for the full layout. This project currently needs a new maintainer -- "
            "see the 'seeking maintainer' status on the project page.",
            "architecture", maintainer2["id"],
        )

        print("Creating mentorship requests...")
        mentorship_service.request_mentorship(
            grade_tracker["id"], student2["id"], "I'd love guidance on structuring the CLI and writing tests.", mentor_id=mentor1["id"]
        )
        req = mentorship_service.request_mentorship(
            campus_connect["id"], student1["id"], "Looking for feedback on my search implementation approach.", mentor_id=mentor1["id"]
        )
        mentorship_service.accept_request(req.id, mentor1["id"])

        print("Setting up collaboration tags & verified contributions...")
        tag1 = projects_service.add_collaboration_tag(campus_connect["id"], "Frontend Development", student1["id"])
        projects_service.approve_collaboration_tag(tag1.id, maintainer1["id"])

        tag2 = projects_service.add_collaboration_tag(campus_connect["id"], "Search & Indexing", student1["id"])
        projects_service.approve_collaboration_tag(tag2.id, maintainer1["id"])

        tag3 = projects_service.add_collaboration_tag(line_follower["id"], "Firmware & Embedded", maintainer2["id"])
        projects_service.approve_collaboration_tag(tag3.id, maintainer2["id"])

        projects_service.record_verified_contribution(
            campus_connect["id"], student1["id"], "pull_request",
            "Implemented search bar and debounce filtering", "PR #14 merged", maintainer1["id"]
        )
        projects_service.record_verified_contribution(
            grade_tracker["id"], student2["id"], "issue_resolved",
            "Resolved GPA cumulative calculation precision issue", "Issue #3 closed", maintainer1["id"]
        )

        print("Posting announcements...")
        announcements_service.post_announcement(
            "Welcome to OpenCampus OSS",
            "This platform is now live for all technical clubs. Browse projects, claim your first issue, "
            "and don't forget to fill out your profile with your skills!",
            admin["id"], club_id=None,
        )
        announcements_service.post_announcement(
            "Hack Night this Friday",
            "Bring your laptop -- we'll be working through the open issues board together in the CS lab.",
            maintainer1["id"], club_id=cs_club["id"],
        )

        print("\nSeed complete. Demo accounts (all use password: password123):")
        print("  admin@opencampus.dev          (platform_admin)")
        print("  arjun.k@opencampus.dev        (project owner / club admin)")
        print("  sara.j@opencampus.dev         (project owner / club admin)")
        print("  mentor.das@opencampus.dev     (mentor)")
        print("  student.meera@opencampus.dev  (student contributor)")
        print("  student.karthik@opencampus.dev(student contributor)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Delete the existing database file before seeding.")
    args = parser.parse_args()

    flask_app = create_app()

    if args.reset:
        db_path = Path(flask_app.config["DATABASE_PATH"])
        if db_path.exists():
            db_path.unlink()
            print(f"Removed existing database at {db_path}")
        flask_app = create_app()  # re-run migrations against the fresh file

    seed(flask_app)
