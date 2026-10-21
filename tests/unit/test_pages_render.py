"""
Every page renders, with the template it is meant to. A template name is only checked when its page is
rendered, so a misspelled or stale one (say after renaming the templates) would otherwise only show
up as a 500 for whoever opens that page.
"""
import os
import re
from contextlib import contextmanager

import pytest
from flask import template_rendered

import server.views as views
from server import app as flask_app
from server.models import Offering

EXAM_URL = '/offerings/1234567/exams/midterm1'
# templates that are only extended or imported by others, never rendered as a page
LAYOUT_TEMPLATES = {'base.html', 'macros.html'}

STAFF_PAGES = [
    ('/offerings', 'select_offering.html'),
    ('/offerings/1234567/', 'select_exam.html'),
    ('/offerings/1234567/exams/new/', 'upsert_exam.html'),
    (f'{EXAM_URL}/', 'exam.html'),
    (f'{EXAM_URL}/edit/', 'upsert_exam.html'),
    (f'{EXAM_URL}/rooms/import/', 'new_room.html'),
    (f'{EXAM_URL}/rooms/import/from_custom_sheet/', 'new_room.html'),
    (f'{EXAM_URL}/rooms/import/from_master_sheet/', 'new_room.html'),
    (f'{EXAM_URL}/rooms/import/from_csv_upload/', 'new_room.html'),
    (f'{EXAM_URL}/rooms/import/from_manual/', 'upsert_room.html'),
    (f'{EXAM_URL}/rooms/1/', 'room.html'),
    (f'{EXAM_URL}/rooms/1/edit', 'upsert_room.html'),
    (f'{EXAM_URL}/students/', 'students.html'),
    (f'{EXAM_URL}/students/import/', 'new_students.html'),
    (f'{EXAM_URL}/students/import/from_custom_sheet/', 'new_students.html'),
    (f'{EXAM_URL}/students/import/from_canvas_roster/', 'new_students.html'),
    (f'{EXAM_URL}/students/import/from_csv_upload/', 'new_students.html'),
    (f'{EXAM_URL}/students/import/from_manual_input/', 'new_students.html'),
    (f'{EXAM_URL}/students/delete/', 'delete_students.html'),
    (f'{EXAM_URL}/students/edit', 'edit_students.html'),
    (f'{EXAM_URL}/students/assign/', 'assign.html'),
    (f'{EXAM_URL}/students/email/', 'email.html'),
    (f'{EXAM_URL}/students/1', 'student.html'),
    (f'{EXAM_URL}/students/1/edit', 'edit_students.html'),
    (f'{EXAM_URL}/students/1/assign/', 'assign_single.html'),
    (f'{EXAM_URL}/students/1/email/', 'email.html'),
    ('/seats/1/', 'seat.html'),
    ('/layouts/preview/', 'preview_layout.html'),
]
# rendered by test_add_courses_page_renders: it redirects when every course you teach is already added
ADD_COURSES_PAGE = ('/offerings/new', 'new_offerings.html')
LOGGED_OUT_PAGES = [
    ('/', 'index.html'),
    ('/dev_login/', 'dev_login.html'),
]


@contextmanager
def rendered_templates():
    names = []

    def record(sender, template, context, **extra):
        names.append(template.name)

    template_rendered.connect(record, flask_app)
    try:
        yield names
    finally:
        template_rendered.disconnect(record, flask_app)


@pytest.fixture(autouse=True)
def master_sheet(monkeypatch):
    # the master sheet page lists the sheet's tabs from Google Sheets
    monkeypatch.setattr(views, 'get_spreadsheet_tabs', lambda sheet_url: ['Soda 999'])


@pytest.mark.parametrize('path, template', STAFF_PAGES)
def test_staff_page_renders(seeded_db, login_as, path, template):
    with rendered_templates() as names:
        response = login_as(1).get(path)
    assert response.status_code == 200, response.get_data(as_text=True)[:500]
    assert names == [template]


@pytest.mark.parametrize('path, template', LOGGED_OUT_PAGES)
def test_logged_out_page_renders(seeded_db, client, path, template):
    with rendered_templates() as names:
        response = client.get(path)
    assert response.status_code == 200
    assert names == [template]


def test_add_courses_page_renders(seeded_db, login_as):
    # Jimmy Xu (user 2) is a TA of course 2345678, which has no exams: take it out to have one to add
    seeded_db.session.delete(Offering.query.filter_by(canvas_id='2345678').one())
    seeded_db.session.commit()
    path, template = ADD_COURSES_PAGE
    with rendered_templates() as names:
        response = login_as(2).get(path)
    assert response.status_code == 200
    assert names == [template]


def test_every_template_is_used():
    templates_dir = os.path.join(flask_app.root_path, flask_app.template_folder)
    pages = {template for _, template in STAFF_PAGES + LOGGED_OUT_PAGES + [ADD_COURSES_PAGE]}
    assert set(os.listdir(templates_dir)) == pages | LAYOUT_TEMPLATES


def test_every_template_name_in_the_code_exists():
    # also the ones only reached on an error path, like a failed form
    templates_dir = os.path.join(flask_app.root_path, flask_app.template_folder)
    existing = set(os.listdir(templates_dir))
    sources = []
    for folder, _, files in os.walk(flask_app.root_path):
        sources += [os.path.join(folder, f) for f in files if f.endswith(('.py', '.html'))]
    named = set()
    for path in sources:
        text = open(path).read()
        named |= set(re.findall(r"render_template\(\s*['\"]([^'\"]+)['\"]", text))
        named |= set(re.findall(r"{%\s*(?:extends|import|include)\s+['\"]([^'\"]+)['\"]", text))
    assert named and named <= existing, named - existing


def test_student_edit_with_overlapping_preferences_shows_the_form_again(seeded_db, login_as):
    # used to render a template that no longer existed, a 500
    client = login_as(1)
    url = f'{EXAM_URL}/students/1/edit'
    page = client.get(url).get_data(as_text=True)
    token = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', page).group(1)
    with rendered_templates() as names:
        response = client.post(url, data={'csrf_token': token, 'new_email': 'jx@berkeley.edu',
                                          'wants': 'lefty', 'avoids': 'lefty', 'submit': 'y'})
    assert response.status_code == 200
    assert names == ['edit_students.html']
    assert 'Wants and avoids should not overlap.' in response.get_data(as_text=True)
