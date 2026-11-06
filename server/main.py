"""The app gunicorn serves (server.main:app) and `flask --app server.main` runs."""
from server.application import create_app

app = create_app()
