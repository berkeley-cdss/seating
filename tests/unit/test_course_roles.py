"""
/offerings lists the user's courses from Canvas, and saves their roles from that list, so that every
course it lists opens. The mock Canvas has Jimmy Xu (user 2) as a student of 1234567 and a TA of 2345678.
"""
from server.models import User, db


def _forget_roles(user_id):
    user = db.session.get(User, user_id)
    user.staff_offerings = set()
    user.student_offerings = {'3456789'}
    db.session.commit()


def test_offerings_page_saves_roles_from_canvas(seeded_db, login_as):
    _forget_roles(2)
    assert login_as(2).get('/offerings').status_code == 200
    user = db.session.get(User, 2)
    assert user.staff_offerings == {'2345678'}
    assert user.student_offerings == {'1234567'}


def test_course_added_since_sign_in_opens_after_offerings_page(seeded_db, login_as):
    _forget_roles(2)
    client = login_as(2)
    assert client.get('/offerings/1234567/').status_code == 403
    client.get('/offerings')
    assert client.get('/offerings/1234567/').status_code == 200


def test_course_removed_since_sign_in_closes_after_offerings_page(seeded_db, login_as):
    _forget_roles(2)
    client = login_as(2)
    client.get('/offerings')
    assert client.get('/offerings/3456789/').status_code == 403
