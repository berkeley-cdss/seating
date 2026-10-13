import re
from unittest.mock import patch

from server import app
from server.models import Room, Seat

EXAM_URL = '/offerings/1234567/exams/midterm1'
STUDENT_URL = f'{EXAM_URL}/students/234567'


def _seat_links(response):
    """Returns the hrefs of links wrapping a seat in the room diagram, keyed by seat id."""
    html = response.get_data(as_text=True)
    return {seat_id: href for href, seat_id in
            re.findall(r'<a href="([^"]+)"[^>]*>\s*<div id="(\d*)" class="s seat', html)}


def test_room_page_links_assigned_seat_to_student(seeded_db, login_as):
    # seat 1 is assigned to the student with canvas id 234567
    response = login_as(1).get(f'{EXAM_URL}/rooms/1/')
    assert response.status_code == 200
    assert _seat_links(response)['1'] == STUDENT_URL


def test_room_page_links_unassigned_seats_to_shareable_link(seeded_db, login_as):
    response = login_as(1).get(f'{EXAM_URL}/rooms/1/')
    assert response.status_code == 200
    links = _seat_links(response)
    for seat_id in ('2', '3', '4'):
        assert links[seat_id] == f'/seats/{seat_id}/'


def test_public_seat_page_has_no_seat_links(seeded_db, client):
    response = client.get('/seats/2/')
    assert response.status_code == 200
    assert _seat_links(response) == {}


def test_assign_page_seats_are_not_links(seeded_db, login_as):
    # staff click a seat here to fill in the Seat ID field, so seats must not navigate away
    response = login_as(1).get(f'{STUDENT_URL}/assign/')
    assert response.status_code == 200
    assert _seat_links(response) == {}


def test_room_preview_renders_unsaved_seats(seeded_db, login_as, monkeypatch):
    # a previewed room isn't saved yet, so its seats have no ids to link to
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', False)
    preview = Room(name='preview', display_name='Preview')
    preview.seats = [
        Seat(name='A1', row='A', seat='1', fixed=True, x=0, y=0, attributes=set()),
        Seat(name='A2', row='A', seat='2', fixed=True, x=1, y=0, attributes=set()),
    ]
    with patch('server.views.get_room_from_google_spreadsheet', return_value=preview):
        response = login_as(1).post(f'{EXAM_URL}/rooms/import/from_custom_sheet/', data={
            'display_name': 'Preview',
            'sheet_url': 'https://docs.google.com/spreadsheets/d/abc/edit',
            'sheet_range': 'Sheet1',
            'preview_room': 'preview',
        })
    assert response.status_code == 200
    assert 'class="s seat"' in response.get_data(as_text=True)
    assert _seat_links(response) == {}
