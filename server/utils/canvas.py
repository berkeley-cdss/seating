from canvasapi import Canvas

from server import app
from server.utils.stub import get_dev_user, get_dev_course, get_dev_user_courses


def _get_client(key):
    return Canvas(app.config['CANVAS_SERVER_URL'], key)


def get_user(canvas_id, key=None):
    if app.config['FLASK_ENV'] == 'development':
        return get_dev_user(canvas_id)
    return _get_client(key).get_user(canvas_id)


def get_course(canvas_id, key=None):
    if app.config['FLASK_ENV'] == 'development':
        return get_dev_course(canvas_id)
    return _get_client(key).get_course(canvas_id)


def get_user_courses(user):
    if app.config['FLASK_ENV'] == 'development':
        return get_dev_user_courses(user['id'])
    return user.get_courses(enrollment_status='active')
