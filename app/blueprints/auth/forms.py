"""
Flask-WTF forms for user authentication and profile management.
"""
from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Email, Length


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    secret_code = PasswordField("Admin Secret Code (Admins only)")
    submit = SubmitField("Sign in")


class RegisterForm(FlaskForm):
    full_name = StringField("Full name", validators=[DataRequired(), Length(max=255)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8)])
    role = SelectField(
        "I am joining as a",
        choices=[("student", "Student contributor"), ("mentor", "Mentor")],
        default="student",
    )
    submit = SubmitField("Create account")


class ProfileForm(FlaskForm):
    full_name = StringField("Full name", validators=[DataRequired(), Length(max=255)])
    bio = TextAreaField("Bio")
    skills = StringField("Skills")
    age_category = SelectField("Age category", choices=[
        ("", "Prefer not to say"),
        ("Under 18", "Under 18"),
        ("18-24", "18-24"),
        ("25-34", "25-34"),
        ("35-44", "35-44"),
        ("45-54", "45-54"),
        ("55+", "55+"),
        ("Prefer not to say", "Prefer not to say"),
    ])
    contact_email = StringField("Contact email")
    discord_handle = StringField("Discord handle")
    linkedin_url = StringField("LinkedIn URL")
    github_url = StringField("GitHub URL")
    submit = SubmitField("Save profile")
