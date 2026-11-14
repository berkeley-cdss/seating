"""
The student export puts an apostrophe before any cell a spreadsheet would run as a formula, as
sections does, and importing that file back drops it, so the export still round-trips.
"""
import csv
import html
import io
import re

import pytest

from server.models import db, Student
from server.services.csv import csv_safe, from_csv_safe

EXAM_URL = '/offerings/1234567/exams/midterm1'
FORMULA_NAME = '=HYPERLINK("https://example.com","Ana")'
OPTIONS = {
    'revalidate_existing_assignments': 'y', 'assignment_import_strategy': 'revalidate',
    'updated_student_info_import_strategy': 'merge', 'updated_preference_import_strategy': 'overwrite',
    'new_student_import_strategy': 'append', 'missing_student_import_strategy': 'ignore',
}


@pytest.mark.parametrize('value, cell', [
    ('=1+1', "'=1+1"), ('+1', "'+1"), ('-1', "'-1"), ('@SUM(A1)', "'@SUM(A1)"),
    ('\t=1', "'\t=1"), ('\r=1', "'\r=1"),
    ('Ana', 'Ana'), ("'Ana", "'Ana"), ('', ''), (None, ''), (12, '12'),
])
def test_csv_safe(value, cell):
    assert csv_safe(value) == cell


@pytest.mark.parametrize('value', ['=1+1', '+1', '-1', '@SUM(A1)', '\t=1', 'Ana', "'Ana", "'", ''])
def test_from_csv_safe_undoes_csv_safe(value):
    assert from_csv_safe(csv_safe(value)) == value


def test_from_csv_safe_leaves_other_apostrophes():
    assert from_csv_safe("'Ana") == "'Ana"
    assert from_csv_safe(None) is None


@pytest.fixture
def staff(seeded_db, login_as):
    student = db.session.get(Student, 1)
    student.name = FORMULA_NAME
    student.wants = {'=lefty'}
    db.session.commit()
    return login_as(1)


def _export(client):
    response = client.get(EXAM_URL + '/students/export/csv')
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_export_makes_formula_cells_text(staff):
    rows = list(csv.reader(io.StringIO(_export(staff))))
    header, cells = rows[0], [cell for row in rows[1:] for cell in row]
    assert "'=lefty" in header
    assert "'" + FORMULA_NAME in cells
    for row in rows:
        assert not any(cell[:1] in ('=', '+', '-', '@', '\t', '\r') for cell in row)


def test_an_export_imports_back_as_it_was(staff):
    exported = _export(staff)
    student = db.session.get(Student, 1)
    student.name, student.wants = 'Changed', set()
    db.session.commit()

    page = staff.get(EXAM_URL + '/students/import/').get_data(as_text=True)
    token = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', page).group(1)
    response = staff.post(EXAM_URL + '/students/import/', data={
        'csrf_token': token, **OPTIONS, 'file': (io.BytesIO(exported.encode('utf-8')), 'export.csv'),
    }, content_type='multipart/form-data', follow_redirects=True)
    messages = [html.unescape(m) for m in re.findall(r'alert-message">(.*?)</span>', response.get_data(as_text=True))]
    assert any('Import done' in m for m in messages), messages

    db.session.expire_all()
    student = db.session.get(Student, 1)
    assert (student.name, student.wants) == (FORMULA_NAME, {'=lefty'})
