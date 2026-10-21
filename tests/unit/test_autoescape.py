"""
Templates are named *.html.j2, which Flask does not autoescape by default, so student names and
other imported or typed-in data used to be rendered as raw HTML. They must come out escaped.
"""
import os
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


# templates that are deliberately not HTML, and so not escaped (none yet)
NOT_HTML_TEMPLATES = set()


@pytest.mark.parametrize('filename, escaped', [
    ('students.html.j2', True),
    ('feed.xml.j2', True),
    ('icon.svg.j2', True),
    ('email.txt.j2', False),
    ('export.csv.j2', False),
    ('students.html', True),
    (None, True),  # render_template_string
])
def test_autoescape_follows_the_extension_before_j2(filename, escaped):
    assert flask_app.select_jinja_autoescape(filename) is escaped


def test_every_template_is_autoescaped():
    # an HTML template named so that it is not escaped (say foo.j2) would print imported data as
    # raw HTML: name it *.html.j2, or list it in NOT_HTML_TEMPLATES if it really is not HTML
    templates_dir = os.path.join(flask_app.root_path, flask_app.template_folder)
    templates = sorted(os.listdir(templates_dir))
    assert templates
    not_escaped = [t for t in templates if not flask_app.select_jinja_autoescape(t)]
    assert set(not_escaped) == NOT_HTML_TEMPLATES


@pytest.mark.parametrize('path', [
    '/students/',  # students table
    '/rooms/1/',  # seat map tooltip
    '/students/1',  # student page (Jimmy Xu's database id)
    '/students/2/assign/',  # seat maps of the assign page
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
