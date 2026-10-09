import re

import pytest

from server.models import db, Exam, Room, Student, User

STUDENTS_URL = '/offerings/1234567/exams/midterm1/students/'


def _pref_cards(response):
    return re.findall(r'<div class="pref-card">(.*?)</div>', response.get_data(as_text=True))


def test_seeded_users_offerings(seeded_db):
    users = {u.id: u for u in User.query.all()}
    assert users[1].staff_offerings == {'1234567'}
    assert users[1].student_offerings == {'4567890'}
    assert users[2].staff_offerings == {'2345678'}
    assert users[2].student_offerings == {'1234567'}
    assert users[3].staff_offerings == {'3456789'}
    assert users[3].student_offerings == {'1234567', '2345678'}


def test_string_set_rejects_str(seeded_db):
    user = db.session.get(User, 1)
    user.staff_offerings = '1234567'
    with pytest.raises(Exception, match='StringSet expects a collection'):
        db.session.commit()
    db.session.rollback()


def test_students_page_requires_login(seeded_db, client):
    response = client.get(STUDENTS_URL)
    assert response.status_code == 302
    assert '/login' in response.location


def test_students_page_as_staff(seeded_db, login_as):
    response = login_as(1).get(STUDENTS_URL)
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    for student in Student.query.filter_by(exam_id=1):
        assert student.name in page


def test_students_page_redirects_student_to_their_seat(seeded_db, login_as):
    # user 2 is a student in this offering with a seat assignment
    response = login_as(2).get(STUDENTS_URL)
    assert response.status_code == 302
    assert response.location.endswith('/seats/1/')


def test_students_page_forbidden_for_unseated_student(seeded_db, login_as):
    # user 3 is a student in this offering without a seat assignment
    response = login_as(3).get(STUDENTS_URL)
    assert response.status_code == 403
    assert 'You have not been assigned a seat' in response.get_data(as_text=True)


def test_students_page_room_preferences(seeded_db, login_as):
    exam = db.session.get(Exam, 1)
    exam.rooms.append(Room(name='soda888', display_name='Soda 888'))
    db.session.commit()
    live_room = exam.rooms[0]
    student = db.session.get(Student, 1)
    student.room_wants = {str(live_room.id)}
    student.room_avoids = {'4242'}
    db.session.commit()

    response = login_as(1).get(STUDENTS_URL)
    assert response.status_code == 200
    cards = _pref_cards(response)
    assert live_room.name_and_start_at_time_display(short=True) in cards
    assert 'deleted room 4242' in cards
