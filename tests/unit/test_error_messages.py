"""
What staff see when an action fails: messages we write ourselves, never the exception's own text,
which for a database error holds the SQL statement, its parameters (student data) and the database's host.
"""
import io
import re

import pytest
from markupsafe import escape
from sqlalchemy.exc import IntegrityError, OperationalError

import server.views
from server.models import db, Exam, Offering, Room
from server.typings.exception import DataValidationError, GcpError

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
    # some actions also say which exam is active now: only the error matters here
    flashes = [message for category, message in _flashes(client) if category == 'error']
    assert len(flashes) == 1
    message = flashes[0]
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


def _integrity_error(*args, **kwargs):
    raise IntegrityError(SECRET, {'email': 'oski@berkeley.edu'}, Exception('UNIQUE constraint failed'))


EDIT_ROOM = {'display_name': 'Soda 999', 'movable_seats-0-attributes': '', 'movable_seats-0-count': '0', 'submit': 'y'}

# each action, and the start of what it says when the database fails under it
DATABASE_FAILURES = {
    'hide offering': ('/offerings/1234567/hide/', {}, "Couldn't hide Introduction to Software Engineering (Fall 2023)"),
    'create exam': ('/offerings/1234567/exams/new/', {'name': 'final', 'display_name': 'Final', 'submit': 'y'},
                    "Couldn't create exam 'final'"),
    'edit exam': (f'{EXAM_URL}/edit/', {'display_name': 'Midterm One', 'submit': 'y'},
                  "Couldn't edit exam 'Midterm One'"),
    'toggle exam': (f'{EXAM_URL}/toggle/', {}, "Couldn't activate or deactivate exam 'Midterm 1'"),
    'delete room': (f'{EXAM_URL}/rooms/1/delete', {}, "Couldn't delete room 'Soda 999'"),
    'edit room': (f'{EXAM_URL}/rooms/1/edit', EDIT_ROOM, "Couldn't edit room 'Soda 999'"),
    'delete student': (f'{EXAM_URL}/students/1/delete', {}, "Couldn't delete student Jimmy Xu"),
}


@pytest.mark.parametrize('url, data, message_start', DATABASE_FAILURES.values(), ids=DATABASE_FAILURES.keys())
def test_database_errors_hide_the_exception(staff, monkeypatch, url, data, message_start):
    monkeypatch.setattr(db.session, 'commit', _db_error)
    staff.post(url, data=data)
    _assert_unexpected_error_flashed(staff, message_start)


def test_importing_an_offering_hides_the_exception(seeded_db, login_as, monkeypatch):
    # user 2 teaches 2345678: take it out so there is a course to import
    db.session.delete(Offering.query.filter_by(canvas_id='2345678').one())
    db.session.commit()
    monkeypatch.setattr(db.session, 'commit', _db_error)
    response = login_as(2).post('/offerings/new', data={'offerings': '2345678', 'submit': 'y'})
    # the course list stays up to try again
    assert response.status_code == 200
    assert re.search(r"Couldn(&#39;|')t import the course offerings due to an unexpected error"
                     r" \(ref [0-9a-f]{8}\)\.", response.text)
    assert 'oski' not in response.text


def test_exam_created_meanwhile_is_reported_plainly(staff, monkeypatch):
    # another request created it after the check for an existing exam
    monkeypatch.setattr(db.session, 'commit', _integrity_error)
    response = staff.post('/offerings/1234567/exams/new/',
                          data={'name': 'final', 'display_name': 'Final', 'submit': 'y'})
    assert response.status_code == 200
    assert escape("An exam named 'final' already exists in this offering.") in response.text


def test_room_imported_meanwhile_is_reported_plainly(staff, monkeypatch):
    monkeypatch.setattr(db.session, 'commit', _integrity_error)
    staff.post(f'{EXAM_URL}/rooms/import/from_manual/', data={**EDIT_ROOM, 'display_name': 'Cory 277'})
    assert _flashes(staff) == [
        ('error', "A room named 'Cory 277' with that start time already exists in this exam.")]


def test_room_renamed_to_an_existing_room_is_reported_plainly(staff, monkeypatch):
    monkeypatch.setattr(db.session, 'commit', _integrity_error)
    staff.post(f'{EXAM_URL}/rooms/1/edit', data={**EDIT_ROOM, 'display_name': 'Cory 277'})
    assert _flashes(staff) == [
        ('error', "A room named 'Cory 277' with that start time already exists in this exam.")]


@pytest.mark.parametrize('error, message', [
    (DataValidationError('Fixed seat name repeated: A1'),
     "Couldn't edit the seats of room 'Soda 999': Fixed seat name repeated: A1"),
    (OperationalError(SECRET, {}, Exception()), None),
])
def test_editing_room_seats_that_fail(staff, monkeypatch, error, message):
    def fail(*args):
        raise error
    monkeypatch.setattr(server.views, 'update_room_from_manual_input', fail)
    staff.post(f'{EXAM_URL}/rooms/1/edit', data=EDIT_ROOM)
    if message:
        assert _flashes(staff) == [('error', message)]
    else:
        _assert_unexpected_error_flashed(staff, "Couldn't edit the seats of room 'Soda 999'")


def test_custom_sheet_room_error_hides_the_exception(staff, monkeypatch):
    monkeypatch.setattr(server.views, 'get_room_from_google_spreadsheet', _db_error)
    response = staff.post(f'{EXAM_URL}/rooms/import/from_custom_sheet/', data={
        'display_name': 'Cory 277', 'sheet_url': 'https://docs.google.com/spreadsheets/d/abc/edit',
        'sheet_range': 'Cory 277', 'create_room': 'y'})
    # nothing was imported, so the form stays up to fix the sheet
    assert response.status_code == 200
    assert re.search(r"Couldn(&#39;|')t import room (&#39;|')Cory 277(&#39;|') due to an unexpected error"
                     r" \(ref [0-9a-f]{8}\)\.", response.text)
    assert SECRET not in response.text and 'oski' not in response.text


def test_custom_sheet_room_is_saved(staff, monkeypatch):
    monkeypatch.setattr(server.views, 'get_room_from_google_spreadsheet',
                        lambda exam, form: Room(exam_id=exam.id, name='cory277', display_name='Cory 277'))
    staff.post(f'{EXAM_URL}/rooms/import/from_custom_sheet/', data={
        'display_name': 'Cory 277', 'sheet_url': 'https://docs.google.com/spreadsheets/d/abc/edit',
        'sheet_range': 'Cory 277', 'create_room': 'y'})
    assert Room.query.filter_by(exam_id=1, display_name='Cory 277').count() == 1


def test_master_sheet_rooms_report_each_failure(staff, monkeypatch):
    monkeypatch.setattr(server.views, 'get_spreadsheet_tabs', lambda url: ['Cory 277', 'Wheeler 150'])

    def get_room(exam, form):
        if form.display_name.data == 'Cory 277':
            raise GcpError('Sheet is empty')
        return Room(exam_id=exam.id, name='wheeler150', display_name='Wheeler 150')
    monkeypatch.setattr(server.views, 'get_room_from_google_spreadsheet', get_room)
    staff.post(f'{EXAM_URL}/rooms/import/from_master_sheet/',
               data={'rooms': ['Cory 277', 'Wheeler 150'], 'submit': 'y'})
    assert _flashes(staff) == [('error', "Couldn't import room 'Cory 277': Sheet is empty")]
    assert [r.display_name for r in Room.query.filter_by(exam_id=1).order_by(Room.id)] == ['Soda 999', 'Wheeler 150']


def test_canvas_roster_import_error_hides_the_exception(staff, monkeypatch):
    monkeypatch.setattr(server.views, 'get_students_from_canvas', _db_error)
    staff.post(f'{EXAM_URL}/students/import/from_canvas_roster/', data={'submit': 'y'})
    _assert_unexpected_error_flashed(staff, "Couldn't import students from the Canvas roster")


def test_layout_preview_error_hides_the_exception(staff, monkeypatch):
    monkeypatch.setattr(server.views, 'get_layout_preview_from_text', _db_error)
    response = staff.post('/layouts/preview/', data={'text': 'row,seat\nA,1\n'})
    assert re.search(r"Couldn(&#39;|')t preview the layout due to an unexpected error \(ref [0-9a-f]{8}\)\.",
                     response.text)
    assert 'oski' not in response.text
