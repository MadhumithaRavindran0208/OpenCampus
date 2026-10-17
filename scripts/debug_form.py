import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app import create_app

app = create_app()
client = app.test_client()
r = client.get("/projects/?difficulty=beginner")
html = r.data.decode()

# Extract just the <select> elements to see if 'selected' works
for tag in ("difficulty", "status"):
    idx = html.find(f'id="{tag}"')
    end = html.find("</select>", idx) + 9
    print(f"=== {tag} select ===")
    print(html[idx:end])
    print()
