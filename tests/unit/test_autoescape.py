"""
Templates are named *.html.j2, which Flask does not autoescape by default, so student names and
other imported or typed-in data used to be rendered as raw HTML. They must come out escaped.
"""
import re

import pytest

from server import app as flask_app
from server.models import db, Exam, SeatAssignment, Seat, Student

EXAM_URL = '/offerings/1234567/exams/midterm1'
NAME = '<script>alert("x")</script> & co'
ESCAPED_NAME = '&lt;script&gt;alert(&#34;x&#34;)&lt;/script&gt; &amp; co'


@pytest.fixture
def jimmy(seeded_db):
    exam = db.session.get(Exam, 1)
    jimmy = Student.query.filter_by(exam_id=exam.id, canvas_id='234567').one()
    jimmy.name = NAME
    jimmy.assignment = SeatAssignment(seat=db.session.get(Seat, 1))
    db.session.commit()
    yield jimmy


def test_html_j2_templates_are_autoescaped():
    assert flask_app.select_jinja_autoescape('students.html.j2')
    assert flask_app.select_jinja_autoescape('macros.html.j2')


@pytest.mark.parametrize('path', [
    '/students/',  # students table
    '/rooms/1/',  # seat map tooltip
    '/students/234567',  # student page
    '/students/345678/assign/',  # seat maps of the assign page
])
def test_student_name_is_escaped(jimmy, login_as, path):
    page = login_as(1).get(EXAM_URL + path).get_data(as_text=True)
    assert ESCAPED_NAME in page
    assert '<script>alert' not in page


def test_multiline_flash_is_escaped_line_by_line(seeded_db, login_as):
    # the bulk edit form flashes the overlapping wants and avoids it was given, over several lines
    client = login_as(1)
    page = client.get(f'{EXAM_URL}/students/edit').get_data(as_text=True)
    csrf_token = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', page).group(1)
    response = client.post(f'{EXAM_URL}/students/edit', data={
        'csrf_token': csrf_token, 'use_all_emails': 'y', 'submit': 'y',
        'wants': '<b>bold</b>', 'avoids': '<b>bold</b>',
    }, follow_redirects=True)
    message = re.search(r'<span class="alert-message">(.*?)</span>', response.get_data(as_text=True), re.S).group(1)
    assert message.startswith('Wants and avoids should not overlap.<br>Want: ')
    assert '&lt;b&gt;bold&lt;/b&gt;' in message
    assert '<b>' not in message
