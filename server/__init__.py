"""
The seating app. Importing this package does not build the app: create_app() in
server/application.py does, and server/main.py holds the app that gunicorn serves.
"""


def create_app(config=None):
    """Lets `flask --app server` find the app factory, as FLASK_APP=server did before."""
    from server.application import create_app as _create_app
    return _create_app(config)
