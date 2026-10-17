"""Verify filter results end-to-end."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app import create_app

app = create_app()
client = app.test_client()

tests = [
    ("All projects",                  "/projects/"),
    ("Beginner only",                 "/projects/?difficulty=beginner"),
    ("Intermediate only",             "/projects/?difficulty=intermediate"),
    ("Advanced only",                 "/projects/?difficulty=advanced"),
    ("Status=active",                 "/projects/?status=active"),
    ("Status=seeking_maintainer",     "/projects/?status=seeking_maintainer"),
    ("Status=maintenance",            "/projects/?status=maintenance"),
    ("Help Wanted only",              "/projects/?seeking=1"),
    ("Keyword=Python",                "/projects/?q=Python"),
    ("Beginner + Help Wanted",        "/projects/?difficulty=beginner&seeking=1"),
]

for label, url in tests:
    r = client.get(url)
    html = r.data.decode()
    count = html.count("card-title-row")
    empty = "No projects match" in html
    print(f"  {label:<35} -> {count} result(s)  empty={empty}")
