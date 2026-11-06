"""The app gunicorn serves (server.main:app) and `flask --app server.main` runs."""
import logging

from server.application import create_app

app = create_app()

# Log to stderr under gunicorn, as Cloud Run collects it
app.logger.addHandler(logging.StreamHandler())
app.logger.setLevel(logging.INFO)
