"""
What staff see when an action fails: messages we write ourselves, never the exception's own text,
which for a database error holds the SQL statement, its parameters (student data) and the database's host.
"""
import io
import re

import pytest
from markupsafe import escape
from sqlalchemy.exc import OperationalError

import server.views
from server.models import db, Exam, Room

EXAM_URL = '/offerings/1234567/exams/midterm1'
SECRET = 'INSERT INTO students (email) VALUES (oski@berkeley.edu) -- db.internal:5432'

pytestmark = pytest.mark.app_config(WTF_CSRF_ENABLED=False)


@pytest.fixture
def staff(seeded_db, login_as):
    return login_as(1)


def _flashes(client):
    with client.session_transaction() as session:
        return session.get('_flashes', [])


def _db_error(*args, **kwargs):
    raise OperationalError(SECRET, {'email': 'oski@berkeley.edu'}, Exception('could not connect to db.internal'))


def _assert_unexpected_error_flashed(client, message_start):
    flashes = _flashes(client)
    assert len(flashes) == 1
    category, message = flashes[0]
    assert category == 'error'
    assert re.fullmatch(re.escape(message_start) + r" due to an unexpected error \(ref [0-9a-f]{8}\)\.", message)
    assert 'oski' not in message and 'db.internal' not in message


def test_duplicate_exam_name_is_reported_plainly(staff):
    response = staff.post('/offerings/1234567/exams/new/',
                          data={'name': 'midterm1', 'display_name': 'Midterm 1 again', 'submit': 'y'})
    # the form comes back, filled in, to pick another name
    assert response.status_code == 200
    assert b'Midterm 1 again' in response.data
    assert escape("An exam named 'midterm1' already exists in this offering.") in response.text
    assert Exam.query.filter_by(offering_canvas_id='1234567', name='midterm1').count() == 1


def test_database_error_shows_a_reference_and_logs_the_error(staff, monkeypatch, caplog):
    monkeypatch.setattr(db.session, 'commit', _db_error)
    staff.post(f'{EXAM_URL}/delete/')
    _assert_unexpected_error_flashed(staff, "Couldn't delete exam 'Midterm 1'")
    ref = re.search(r'ref ([0-9a-f]{8})', _flashes(staff)[0][1]).group(1)
    # the full error is in the log, under the same reference
    record = next(r for r in caplog.records if ref in r.getMessage())
    assert record.exc_info and record.exc_info[0] is OperationalError


def test_student_import_error_hides_the_exception(staff, monkeypatch):
    monkeypatch.setattr(server.views, 'get_students_from_import_form', _db_error)
    staff.post(f'{EXAM_URL}/students/import/', data={'text': 'x', 'submit': 'y'})
    _assert_unexpected_error_flashed(staff, "Couldn't import students")


def test_duplicate_room_is_reported_plainly(staff):
    rooms = Room.query.filter_by(exam_id=1).count()
    staff.post(f'{EXAM_URL}/rooms/import/from_csv_upload/', data={
        'display_name': 'Soda 999', 'submit': 'y',
        'file': (io.BytesIO(b'row,seat\nA,1\n'), 'room.csv'),
    }, content_type='multipart/form-data')
    assert _flashes(staff) == [
        ('error', "Couldn't import room 'Soda 999': A room with that name and start time already exists")]
    assert Room.query.filter_by(exam_id=1).count() == rooms


def test_room_save_error_hides_the_exception(staff, monkeypatch):
    monkeypatch.setattr(db.session, 'commit', _db_error)
    staff.post(f'{EXAM_URL}/rooms/import/from_csv_upload/', data={
        'display_name': 'Cory 277', 'submit': 'y',
        'file': (io.BytesIO(b'row,seat\nA,1\n'), 'room.csv'),
    }, content_type='multipart/form-data')
    _assert_unexpected_error_flashed(staff, "Couldn't import room 'Cory 277'")


def test_layout_preview_of_a_file_that_is_not_utf8(staff):
    response = staff.post('/layouts/preview/', data={
        'file': (io.BytesIO('row,seat\nA,1\n'.encode('utf-16')), 'room.csv'), 'submit': 'y',
    }, content_type='multipart/form-data')
    assert response.status_code == 200
    assert escape("Couldn't preview the layout: save the file as CSV with UTF-8 encoding.") in response.text
