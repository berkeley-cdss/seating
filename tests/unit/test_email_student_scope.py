"""
The single-student email page takes a student's database id in its url. Staff are checked against
the exam in the url, so only that exam's students may be loaded there: looked up by id alone, staff
of one course could open any student of any course, prefilled with their email and seat.
"""
import re

import pytest

from server.models import db, Exam, Student

EXAM_URL = '/offerings/1234567/exams/midterm1'


def _add_student(exam, canvas_id, email):
    student = Student(exam_id=exam.id, canvas_id=canvas_id, name='Elsewhere, Student', email=email,
                      wants=set(), avoids=set(), room_wants=set(), room_avoids=set())
    db.session.add(student)
    db.session.commit()
    return student


@pytest.fixture
def other_course_student(seeded_db):
    # user 1 is staff of offering 1234567 only, not 2345678
    exam = Exam(offering_canvas_id='2345678', name='final', display_name='Final', is_active=True)
    db.session.add(exam)
    db.session.commit()
    return _add_student(exam, '999001', 'other.course@berkeley.edu')


@pytest.fixture
def other_exam_student(seeded_db):
    exam = Exam(offering_canvas_id='1234567', name='midterm2', display_name='Midterm 2', is_active=True)
    db.session.add(exam)
    db.session.commit()
    return _add_student(exam, '999002', 'other.exam@berkeley.edu')


def test_own_student_is_prefilled(seeded_db, login_as):
    jimmy = Student.query.filter_by(exam_id=1, canvas_id='234567').one()
    page = login_as(1).get(f'{EXAM_URL}/students/email/{jimmy.id}/').get_data(as_text=True)
    assert re.search(rf'id="to_addr"[^>]*value="{re.escape(jimmy.email)}"', page)


def test_students_page_link_opens_the_email_page(seeded_db, login_as):
    client = login_as(1)
    page = client.get(f'{EXAM_URL}/students/').get_data(as_text=True)
    url = re.search(r"location.href = '([^']*/students/email/\d+/)'", page).group(1)
    assert client.get(url).status_code == 200


@pytest.mark.parametrize('fixture', ['other_course_student', 'other_exam_student'])
def test_student_of_another_exam_is_not_found(request, login_as, fixture):
    student = request.getfixturevalue(fixture)
    response = login_as(1).get(f'{EXAM_URL}/students/email/{student.id}/')
    assert response.status_code == 404
    assert student.email not in response.get_data(as_text=True)


def test_posting_for_a_student_of_another_course_is_not_found(other_course_student, login_as):
    response = login_as(1).post(f'{EXAM_URL}/students/email/{other_course_student.id}/', data={'subject': 'x'})
    assert response.status_code == 404


def test_non_numeric_id_is_not_found(seeded_db, login_as):
    assert login_as(1).get(f'{EXAM_URL}/students/email/abc/').status_code == 404
