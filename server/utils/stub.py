DEV_USER_DB = {
    '123456': {
        'id': 123456,
        'name': 'Yu Long',
        'global_id': '10000000000000',
        'effective_locale': 'en'
    }
}


def get_dev_user(user_id):
    return DEV_USER_DB[str(user_id)]


DEV_COURSE_DB = {
    '1234567': {
        'id': 1234567,
        'name': 'Introduction to Software Engineering (Fall 2023)',
        'sis_course_id': 'CRS:COMPSCI-169A-2023-D',
        'course_code': 'COMPSCI 169A-LEC-001',

    }
}


def get_dev_course(course_id):
    return DEV_COURSE_DB[str(course_id)]


DEV_ENROLLMENT_DB = {
    '123456': {
        '1234567':
            {
                'enrollments': [
                    {'type': 'ta', 'role': 'TaEnrollment', 'enrollment_state': 'active'}
                ]
            }
    }
}


def get_dev_user_courses(user_id):
    dic = DEV_ENROLLMENT_DB[str(user_id)]
    return [DEV_COURSE_DB[str(course_id)] | dic[str(course_id)] for course_id in dic.keys()]


DEV_OAUTH_RESP = \
    {
        'access_token': 'dev_access_token',
        'token_type': 'Bearer',
        'user': DEV_USER_DB[str(123456)],
        'canvas_region': 'us-east-1',
        'refresh_token': 'dev_refresh_token',
        'expires_in': 3600
    }
