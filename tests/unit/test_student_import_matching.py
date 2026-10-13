"""
Importing students must not create duplicates (issue #42). A row is matched to a student by
canvas id, falling back to student id, then email, and a student listed on several rows is
created once. The seed exam has Jimmy Xu (234567), Sharon Lovera (345678) and Lavender Angela (456789).
"""
import io
import re

import pytest
from werkzeug.datastructures import FileStorage

from server import app as flask_app
from server.models import db, Exam, Student, User
from server.services.core.student import normalize_id, prepare_students
from server.services.csv import parse_csv, parse_csv_str

EXAM_URL = '/offerings/1234567/exams/midterm1'
HEADER = 'email,name,canvas id,student id\n'


@pytest.fixture
def exam(seeded_db):
    exam = db.session.get(Exam, 1)
    assert len(exam.students) == 3
    jimmy = Student.query.filter_by(exam_id=exam.id, canvas_id='234567').one()
    jimmy.sid = '3031000001'
    jimmy.email = 'jimmy@berkeley.edu'
    db.session.commit()
    yield exam


def _import(exam, csv_text):
    """Runs CSV text through the import like the upload view does, and returns its result."""
    headers, rows = parse_csv_str(csv_text)
    new, updated, invalid, _ = prepare_students(exam, headers, rows)
    db.session.add_all(new + updated)
    db.session.commit()
    return new, updated, invalid


def _students_named(name):
    return Student.query.filter_by(exam_id=1, name=name).all()


@pytest.mark.parametrize('value, expected', [
    ('234567', '234567'),
    (' 234567 ', '234567'),
    ('234567.0', '234567'),
    ('234567.00', '234567'),
    (234567, '234567'),
    ('', None),
    ('  ', None),
    (None, None),
    ('234567.5', '234567.5'),
    ('ab.0', 'ab.0'),
])
def test_normalize_id(value, expected):
    assert normalize_id(value) == expected


@pytest.mark.parametrize('canvas_id', [' 234567', '234567 ', '234567.0'])
def test_canvas_id_from_a_spreadsheet_matches(exam, canvas_id):
    new, updated, invalid = _import(exam, HEADER + f'jimmy@berkeley.edu,Jimmy Xu,{canvas_id},3031000001\n')
    assert (len(new), len(updated), len(invalid)) == (0, 1, 0)
    assert len(_students_named('Jimmy Xu')) == 1


def test_new_canvas_id_is_stored_clean(exam):
    new, _, _ = _import(exam, HEADER + 'new@berkeley.edu,New Student, 777777.0 ,3031000002.0\n')
    assert new[0].canvas_id == '777777'
    assert new[0].sid == '3031000002'


def test_roster_canvas_ids_are_ints(exam):
    # the canvas roster import passes canvas ids as numbers and student ids as None
    rows = [{'canvas id': 234567, 'email': 'jimmy@berkeley.edu', 'name': 'Jimmy Xu', 'student id': None}]
    new, updated, invalid, _ = prepare_students(exam, ['canvas id', 'email', 'name', 'student id'], rows)
    assert (len(new), len(updated), len(invalid)) == (0, 1, 0)
    assert updated[0].sid == '3031000001'


def test_row_without_canvas_id_matches_by_student_id(exam):
    new, updated, invalid = _import(exam, HEADER + 'other@berkeley.edu,Jimmy X,,3031000001\n')
    assert (len(new), len(updated), len(invalid)) == (0, 1, 0)
    assert updated[0].canvas_id == '234567'
    assert updated[0].name == 'Jimmy X'


def test_row_without_canvas_id_matches_by_email_ignoring_case(exam):
    new, updated, invalid = _import(exam, HEADER + ' JIMMY@Berkeley.edu ,Jimmy X,,\n')
    assert (len(new), len(updated), len(invalid)) == (0, 1, 0)
    assert updated[0].canvas_id == '234567'


def test_student_id_is_tried_before_email(exam):
    # the student id is Jimmy's, the email Sharon's: the student id wins
    sharon = Student.query.filter_by(exam_id=1, canvas_id='345678').one()
    _, updated, _ = _import(exam, HEADER + f'{sharon.email},Someone,,3031000001\n')
    assert updated[0].canvas_id == '234567'


def test_row_without_canvas_id_or_match_is_invalid(exam):
    new, updated, invalid = _import(exam, HEADER + 'nobody@berkeley.edu,Nobody,,3039999999\n')
    assert (len(new), len(updated), len(invalid)) == (0, 0, 1)


@pytest.mark.parametrize('row', [
    'jimmy@berkeley.edu,Jimmy Xu,999999,\n',  # Jimmy's email
    'someone@berkeley.edu,Jimmy Xu,999999,3031000001\n',  # Jimmy's student id
])
def test_existing_student_with_another_canvas_id_is_invalid(exam, row):
    new, updated, invalid = _import(exam, HEADER + row)
    assert (len(new), len(updated), len(invalid)) == (0, 0, 1)
    assert len(_students_named('Jimmy Xu')) == 1
    assert Student.query.filter_by(exam_id=1, canvas_id='999999').count() == 0


def test_student_listed_twice_is_created_once(exam):
    new, updated, invalid = _import(exam, HEADER + 'new@berkeley.edu,New Student,777777,3031000002\n'
                                                   'NEW@berkeley.edu,New Student,777777.0,3031000002\n')
    assert (len(new), len(updated), len(invalid)) == (1, 0, 0)
    assert len(_students_named('New Student')) == 1


def test_later_row_of_a_new_student_updates_it(exam):
    new, _, _ = _import(exam, 'email,name,canvas id,lefty\n'
                              'new@berkeley.edu,New Student,777777,false\n'
                              'new@berkeley.edu,New Student,777777,true\n')
    assert len(new) == 1
    assert new[0].wants == {'lefty'}
    assert new[0].avoids == set()


def test_new_student_listed_again_without_canvas_id_is_not_duplicated(exam):
    new, updated, invalid = _import(exam, HEADER + 'new@berkeley.edu,New Student,777777,3031000002\n'
                                                   'new@berkeley.edu,New Student,,\n')
    assert (len(new), len(updated), len(invalid)) == (1, 0, 0)
    assert len(_students_named('New Student')) == 1


def test_new_student_listed_again_with_another_canvas_id_is_invalid(exam):
    new, updated, invalid = _import(exam, HEADER + 'new@berkeley.edu,New Student,777777,3031000002\n'
                                                   'new@berkeley.edu,New Student,888888,3031000002\n')
    assert (len(new), len(updated), len(invalid)) == (1, 0, 1)
    assert len(_students_named('New Student')) == 1


def test_student_listed_twice_can_still_open_the_exam(exam, client):
    # two students with one canvas id used to crash the exam page for that student
    db.session.delete(Student.query.filter_by(exam_id=1, canvas_id='345678').one())
    db.session.commit()
    _import(exam, HEADER + 'sharon@berkeley.edu,Sharon Lovera,345678,\n'
                           'sharon@berkeley.edu,Sharon Lovera,345678,\n')
    assert Student.query.filter_by(exam_id=1, canvas_id='345678').count() == 1

    sharon = User.query.filter_by(canvas_id='345678').one()
    with client.session_transaction() as session:
        session['_user_id'] = str(sharon.id)
        session['_fresh'] = True
    response = client.get(f'{EXAM_URL}/')
    # not seated yet, which the page explains instead of crashing
    assert response.status_code == 403
    assert 'You have not been assigned a seat' in response.get_data(as_text=True)


def test_parse_csv_reads_excel_utf8_files():
    file = FileStorage(io.BytesIO('﻿Email,Name,Canvas ID\nx@berkeley.edu,X,1\n'.encode('utf-8')))
    headers, rows = parse_csv(file)
    assert headers == ['email', 'name', 'canvas id']
    assert rows == [{'email': 'x@berkeley.edu', 'name': 'X', 'canvas id': '1'}]


def test_upload_excel_utf8_csv(exam, login_as):
    client = login_as(1)
    page = client.get(f'{EXAM_URL}/students/import/').get_data(as_text=True)
    csrf_token = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', page).group(1)
    csv_bytes = ('﻿' + HEADER + 'jimmy@berkeley.edu,Jimmy Xu,234567.0,3031000001\n'
                 'new@berkeley.edu,New Student,777777,3031000002\n').encode('utf-8')
    response = client.post(f'{EXAM_URL}/students/import/from_csv_upload/', data={
        'csrf_token': csrf_token,
        'file': (io.BytesIO(csv_bytes), 'roster.csv'),
        'revalidate_existing_assignments': 'y',
        'assignment_import_strategy': 'revalidate',
        'updated_student_info_import_strategy': 'merge',
        'updated_preference_import_strategy': 'overwrite',
        'new_student_import_strategy': 'append',
        'missing_student_import_strategy': 'ignore',
    }, content_type='multipart/form-data', follow_redirects=True)
    assert 'Import done. 1 new students, 1 updated students 0 invalid students' in response.get_data(as_text=True)
    assert len(_students_named('Jimmy Xu')) == 1
    assert Student.query.filter_by(exam_id=1).count() == 4
