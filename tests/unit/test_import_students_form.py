"""
Students are imported from one form (issue #142): an uploaded file, pasted rows or a Google Sheets link.
Files and pasted rows may be comma or tab separated, so rows copied straight out of a spreadsheet can be
pasted. The Canvas roster keeps its own form. The seed exam has three students.
"""
import io
import re

import pytest

import server.services.core.data as data
from server.models import db, Student

EXAM_URL = '/offerings/1234567/exams/midterm1'
IMPORT_URL = f'{EXAM_URL}/students/import/'
CSV = 'canvas id,email,name,lefty\n777777,new@berkeley.edu,New Student,true\n'
TSV = 'canvas id\temail\tname\tlefty\n777777\tnew@berkeley.edu\tNew Student\ttrue\n'
OPTIONS = {
    'revalidate_existing_assignments': 'y', 'assignment_import_strategy': 'revalidate',
    'updated_student_info_import_strategy': 'merge', 'updated_preference_import_strategy': 'merge',
    'new_student_import_strategy': 'append', 'missing_student_import_strategy': 'ignore',
}


@pytest.fixture
def staff(seeded_db, login_as):
    return login_as(1)


def _import(client, **fields):
    page = client.get(IMPORT_URL).get_data(as_text=True)
    token = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', page).group(1)
    response = client.post(IMPORT_URL, data={'csrf_token': token, **OPTIONS, **fields},
                           content_type='multipart/form-data', follow_redirects=True)
    messages = [' '.join(m.split()) for m in
                re.findall(r'<span class="alert-message">(.*?)</span>', response.get_data(as_text=True), re.S)]
    return response, messages


def _new_student():
    db.session.expire_all()
    return Student.query.filter_by(exam_id=1, canvas_id='777777').one_or_none()


@pytest.mark.parametrize('text', [CSV, TSV, CSV.replace('\n', '\r\n'), '﻿' + TSV])
def test_paste_comma_or_tab_separated_rows(staff, text):
    _, messages = _import(staff, text=text)
    assert 'Import done. 1 new students' in messages[0]
    assert _new_student().wants == {'lefty'}


@pytest.mark.parametrize('filename, content', [('roster.csv', CSV), ('roster.tsv', TSV), ('roster.txt', TSV)])
def test_upload_a_csv_or_tsv_file(staff, filename, content):
    _, messages = _import(staff, file=(io.BytesIO(content.encode('utf-8')), filename))
    assert 'Import done. 1 new students' in messages[0]
    assert _new_student().wants == {'lefty'}


def test_upload_rejects_other_files(staff):
    response, messages = _import(staff, file=(io.BytesIO(b'PK\x03\x04'), 'roster.xlsx'))
    assert response.status_code == 200
    assert messages == ['file: Choose a CSV or TSV file']
    assert _new_student() is None


@pytest.fixture
def sheet(monkeypatch):
    """A Google Sheet with two tabs; records which tab was read."""
    read = []

    def tab_content(sheet_url, tab):
        read.append(tab)
        headers, rows = data.parse_csv_str(CSV)
        return headers, rows

    monkeypatch.setattr(data, 'get_spreadsheet_tabs', lambda sheet_url: ['Roster', 'Other'])
    monkeypatch.setattr(data, 'get_spreadsheet_tab_content', tab_content)
    return read


@pytest.mark.parametrize('tab, read', [('', 'Roster'), ('Other', 'Other')])
def test_google_sheet_link(staff, sheet, tab, read):
    _, messages = _import(staff, sheet_url='https://docs.google.com/spreadsheets/d/abc123/edit', sheet_range=tab)
    assert 'Import done. 1 new students' in messages[0]
    assert sheet == [read]  # without a tab, the first one
    assert _new_student() is not None


def test_nothing_to_import(staff):
    response, messages = _import(staff)
    assert response.status_code == 200
    assert messages == ['Choose a file, paste a roster or enter a Google Sheets link to import']
    assert Student.query.filter_by(exam_id=1).count() == 3


def test_first_source_given_is_used(staff, sheet):
    # the page stops this in the browser; the server takes the file, then pasted rows, then a link
    _, messages = _import(staff, file=(io.BytesIO(CSV.encode()), 'roster.csv'),
                          text=CSV.replace('777777', '888888'),
                          sheet_url='https://docs.google.com/spreadsheets/d/abc123/edit')
    assert 'Import done. 1 new students' in messages[0]
    assert _new_student() is not None
    assert Student.query.filter_by(exam_id=1, canvas_id='888888').count() == 0
    assert sheet == []


def test_page_has_one_import_form_and_the_canvas_roster(staff):
    page = staff.get(IMPORT_URL).get_data(as_text=True)
    assert 'mdl-tabs' not in page
    forms = re.findall(r'<form[^>]*action="([^"]+)"', page)
    assert forms == [IMPORT_URL, f'{IMPORT_URL}from_canvas_roster/']
    assert page.count('value="Import"') == 1
    assert 'canvas id</strong>, <strong>email</strong> and <strong>name</strong> are required' in page
