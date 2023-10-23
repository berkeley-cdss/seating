from canvasapi import Canvas

from server import app
from server.utils.stub import get_dev_user, get_dev_course, get_dev_user_courses


def _get_client(key):
    return Canvas(app.config['CANVAS_SERVER_URL'], key)


def is_mock_canvas():
    return app.config['MOCK_CANVAS']


def get_user(canvas_id, key=None):
    if is_mock_canvas():
        return get_dev_user(canvas_id)
    return _get_client(key).get_user(canvas_id)


def get_course(canvas_id, key=None):
    if is_mock_canvas():
        return get_dev_course(canvas_id)
    return _get_client(key).get_course(canvas_id)


def get_user_courses(user):
    if is_mock_canvas():
        return get_dev_user_courses(user['id'])
    return user.get_courses(enrollment_status='active')


def get_user_courses_categorized(user):
    courses_raw = get_user_courses(user)
    staff_courses, student_courses = [], []
    for c in courses_raw:
        # c may be a dict or a Course object
        c_dic = c.__dict__ if hasattr(c, '__dict__') else c
        if 'id' not in c_dic or 'enrollments' not in c_dic:
            continue
        for e in c_dic['enrollments']:
            if e["type"] == 'ta' or e["type"] == 'teacher':
                staff_courses.append(c_dic)
            if e["type"] == 'student':
                student_courses.append(c_dic)
    return staff_courses, student_courses
