"""
The proctor view (issue #75) shows a room's fixed seats turned 180 degrees, as seen from the
front of the room, so A1 is in the lower left instead of the upper right. It is for staff only.
The seed room has seats A1 (id 1), A2 (id 2) in the front row and B1 (id 3), B2 (id 4) behind them.
"""
import html as html_lib
import re
from urllib.parse import parse_qs, urlsplit

from flask import render_template_string

from server import app as flask_app
from server.models import db, Room

EXAM_URL = '/offerings/1234567/exams/midterm1'
ROOM_URL = f'{EXAM_URL}/rooms/1/'


def _seat_positions(html):
    """{seat id: (left, top)} of the seats drawn on the seat map."""
    return {int(seat_id): (float(left), float(top)) for seat_id, left, top in
            re.findall(r'<div id="(\d+)" class="s seat[^"]*" style="left:([\d.-]+)px;top:([\d.-]+)px">', html)}


def _toggle(html):
    """The room view toggle button: its label, path and query."""
    href, label = re.search(r'<a class="mdl-button[^"]*" href="([^"]+)">(Proctor view|Student view)</a>', html).groups()
    url = urlsplit(html_lib.unescape(href))
    return label, url.path, parse_qs(url.query)


def _headings(html):
    """The Front/Back headings around the seat map, top to bottom."""
    return re.findall(r'<h6>(Front|Back)</h6>', html)


def test_room_page_shows_the_student_view_by_default(seeded_db, login_as):
    html = login_as(1).get(ROOM_URL).get_data(as_text=True)
    a1, a2, b1, _ = (_seat_positions(html)[seat_id] for seat_id in (1, 2, 3, 4))
    # facing the front: A1 is in the upper right, A2 to its left, B1 behind it
    assert a2[0] < a1[0] and a1[1] < b1[1]
    assert _headings(html) == ['Front', 'Back']
    assert _toggle(html) == ('Proctor view', ROOM_URL, {'view': ['proctor']})


def test_proctor_view_turns_the_room_around(seeded_db, login_as):
    html = login_as(1).get(f'{ROOM_URL}?view=proctor').get_data(as_text=True)
    a1, a2, b1, b2 = (_seat_positions(html)[seat_id] for seat_id in (1, 2, 3, 4))
    # from the front: A1 is in the lower left, A2 to its right, B1 behind it (above)
    assert a1 == (0, 23) and a2 == (23, 23) and b1 == (0, 0) and b2 == (23, 0)
    assert _headings(html) == ['Back', 'Front']
    # row labels: the left end of the A row is now A1, the right end A2
    labels = {name: (float(left), float(top)) for left, top, name in
              re.findall(r'<div class="seat-label" style="left:([\d.-]+)px;top:([\d.-]+)px">(\w+)</div>', html)}
    assert labels['A1'] == (-50, 23) and labels['A2'] == (53, 23)
    assert _toggle(html) == ('Student view', ROOM_URL, {})


def test_toggle_keeps_the_highlighted_seat(seeded_db, login_as):
    html = login_as(1).get(f'{ROOM_URL}?seat=2').get_data(as_text=True)
    assert _toggle(html) == ('Proctor view', ROOM_URL, {'view': ['proctor'], 'seat': ['2']})
    html = login_as(1).get(f'{ROOM_URL}?seat=2&view=proctor').get_data(as_text=True)
    assert _toggle(html) == ('Student view', ROOM_URL, {'seat': ['2']})


def test_room_without_fixed_seats_has_no_toggle(seeded_db, login_as):
    room = db.session.get(Room, 1)
    for seat in room.fixed_seats:
        db.session.delete(seat)
    db.session.commit()
    html = login_as(1).get(f'{ROOM_URL}?view=proctor').get_data(as_text=True)
    assert 'Proctor view' not in html and 'Student view' not in html


def test_students_cannot_open_the_proctor_view(seeded_db, login_as):
    # Jimmy is a student of this course: the room page sends him to his own seat instead
    response = login_as(2).get(f'{ROOM_URL}?view=proctor')
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/seats/1/')


def test_public_seat_page_ignores_the_proctor_view(seeded_db, login_as):
    html = login_as(2).get('/seats/1/?view=proctor').get_data(as_text=True)
    assert _headings(html) == ['Front', 'Back']
    assert 'Proctor view' not in html


def test_seat_map_never_turns_around_for_students(seeded_db):
    # the macro only honors `proctor` together with `staff`, whatever a caller passes
    with flask_app.test_request_context():
        room = db.session.get(Room, 1)
        html = render_template_string(
            "{% import 'macros.html.j2' as macros with context %}"
            "{{ macros.room(room, staff=false, proctor=true) }}", room=room)
    assert _headings(html) == ['Front', 'Back']
