"""
Runs axe on every page of the app, signed in as the kind of user who sees it.

Each page must meet WCAG 2.1 AA, which Berkeley requires, and WCAG 2.2 AA, axe's best practices
and Section 508.
"""
import re
from dataclasses import dataclass

import pytest

from server import app as flask_app
from tests.a11y.conftest import BASE_URL, VIOLATIONS_BY_RULE
from tests.a11y.utils import COMPLETE_A11Y_STANDARDS, REQUIRED_A11Y_STANDARDS, assert_no_violations, run_axe, \
    save_report

# seeded users (tests/fixtures/user.json): Yu Long is staff in the seeded offering,
# and Jimmy Xu is a student in it with a seat
STAFF = '123456'
STUDENT = '234567'

EXAM = '/offerings/1234567/exams/midterm1'


@dataclass
class Page:
    name: str
    endpoint: str
    path: str
    user: str = None
    # where the page lands, when visiting it redirects
    lands_on: str = None


PAGES = [
    Page('home', 'index', '/'),
    Page('dev login', 'dev_login.dev_login_page', '/dev_login/'),

    Page('student offerings', 'offerings', '/offerings', STUDENT),
    Page('student offering', 'offering', '/offerings/1234567/', STUDENT),
    Page('student seat', 'student_single_seat', '/seats/1/', STUDENT),
    Page('student exam', 'exam', f'{EXAM}/', STUDENT, lands_on='/seats/1/'),

    Page('offerings', 'offerings', '/offerings', STAFF),
    Page('offering', 'offering', '/offerings/1234567/', STAFF),
    Page('new exam', 'new_exam', '/offerings/1234567/exams/new/', STAFF),
    Page('edit exam', 'edit_exam', f'{EXAM}/edit/', STAFF),
    Page('exam', 'exam', f'{EXAM}/', STAFF),
    Page('import room from custom sheet', 'import_room_from_custom_sheet',
         f'{EXAM}/rooms/import/from_custom_sheet/', STAFF),
    Page('import room from csv', 'import_room_from_csv_upload', f'{EXAM}/rooms/import/from_csv_upload/', STAFF),
    Page('import room manually', 'import_room_manually', f'{EXAM}/rooms/import/from_manual/', STAFF),
    Page('room', 'room', f'{EXAM}/rooms/1/', STAFF),
    Page('edit room', 'edit_room', f'{EXAM}/rooms/1/edit', STAFF),
    Page('students', 'students', f'{EXAM}/students/', STAFF),
    Page('import students', 'import_students', f'{EXAM}/students/import/', STAFF),
    Page('import students from canvas', 'import_students_from_canvas_roster',
         f'{EXAM}/students/import/from_canvas_roster/', STAFF),
    Page('edit students', 'edit_students', f'{EXAM}/students/edit', STAFF),
    Page('delete students', 'delete_students', f'{EXAM}/students/delete/', STAFF),
    Page('assign', 'assign', f'{EXAM}/students/assign/', STAFF),
    Page('email', 'email_all_students', f'{EXAM}/students/email/', STAFF),
    Page('student', 'student', f'{EXAM}/students/1', STAFF),
    Page('edit student', 'edit_student', f'{EXAM}/students/1/edit', STAFF),
    Page('assign student', 'assign_student', f'{EXAM}/students/1/assign/', STAFF),
    Page('email student', 'email_single_student', f'{EXAM}/students/1/email/', STAFF),
    Page('preview layout', 'preview_layout', '/layouts/preview/', STAFF),
]

# GET endpoints that are not audited, and why
SKIPPED_ENDPOINTS = {
    'static': 'not a page',
    'favicon': 'not a page',
    'students_template': 'not a page',
    'student_photo': 'not a page',
    'export_students_as_csv': 'not a page',
    'health.check': 'not a page',
    'health.check_db': 'not a page',
    'health.check_logging': 'not a page',
    'auth.login': 'redirects to the login page',
    'auth.authorized': 'redirects after login',
    'auth.logout': 'redirects after logout',
    'dev_login.mock_authorize': 'redirects during login',
    'add_offerings': 'redirects when every Canvas course is already added, as in the seed data',
    'import_room': 'reads the master room sheet from Google Sheets',
    'import_room_from_master_sheet': 'reads the master room sheet from Google Sheets',
    'delete_offering': 'deletes on GET, then redirects',
    'delete_exam': 'deletes on GET, then redirects',
    'toggle_exam': 'changes the exam on GET, then redirects',
    'delete_room': 'deletes on GET',
    'delete_student': 'deletes on GET, then redirects',
}


def test_every_page_is_audited():
    get_endpoints = {rule.endpoint for rule in flask_app.url_map.iter_rules() if 'GET' in rule.methods}
    audited = {page.endpoint for page in PAGES}
    missing = get_endpoints - audited - set(SKIPPED_ENDPOINTS)
    assert not missing, f"Add these to PAGES or SKIPPED_ENDPOINTS in {__file__}: {sorted(missing)}"
    assert not audited & set(SKIPPED_ENDPOINTS)


def _audit(a11y_site, page, standards, label):
    driver = a11y_site.visit(page.path, page.user)
    assert driver.current_url == BASE_URL + (page.lands_on or page.path)
    # Flask's error pages are titled with their status, e.g. "500 Internal Server Error"
    assert not re.match(r'\d{3} ', driver.title), driver.title
    report = run_axe(driver, standards)
    save_report(f'{page.name} {label}', report)
    for violation in report['violations']:
        VIOLATIONS_BY_RULE[f"{violation['id']} ({label})"].add(page.name)
    assert_no_violations(report)


@pytest.mark.parametrize('page', PAGES, ids=[page.name for page in PAGES])
def test_meets_wcag_21_aa(a11y_site, page):
    _audit(a11y_site, page, REQUIRED_A11Y_STANDARDS, 'WCAG 2.1 AA')


@pytest.mark.parametrize('page', PAGES, ids=[page.name for page in PAGES])
def test_meets_wcag_22_aa(a11y_site, page):
    _audit(a11y_site, page, COMPLETE_A11Y_STANDARDS, 'WCAG 2.2 AA')
