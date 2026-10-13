"""
The students page and the student page link to a student's seat as the room page with ?seat=<id>,
which should highlight that seat. The seed room has fixed seats A1-B2 (ids 1-4, Jimmy Xu in A1)
and movable seats 5-7.
"""
import re

EXAM_URL = '/offerings/1234567/exams/midterm1'
ROOM_URL = f'{EXAM_URL}/rooms/1/'


def _highlighted(html):
    """Ids of the seats drawn highlighted, fixed or movable."""
    return [int(seat_id) for seat_id in re.findall(r'class="s (?:seat )?highlight" id=(\d+)', html)] + \
        [int(seat_id) for seat_id in re.findall(r'<div id="(\d+)" class="s seat highlight"', html)]


def test_room_page_highlights_the_seat(seeded_db, login_as):
    html = login_as(1).get(f'{ROOM_URL}?seat=2').get_data(as_text=True)
    assert _highlighted(html) == [2]


def test_highlight_shows_over_an_occupied_seat(seeded_db, login_as):
    html = login_as(1).get(f'{ROOM_URL}?seat=1').get_data(as_text=True)
    assert _highlighted(html) == [1]


def test_link_from_students_page_highlights_the_seat(seeded_db, login_as):
    client = login_as(1)
    page = client.get(f'{EXAM_URL}/students/').get_data(as_text=True)
    link = re.search(r'<a class="assignment" href="([^"]+)"', page).group(1).replace('&amp;', '&')
    assert link == f'{ROOM_URL}?seat=1'
    assert _highlighted(client.get(link).get_data(as_text=True)) == [1]


def test_bad_seat_parameter_highlights_nothing(seeded_db, login_as):
    response = login_as(1).get(f'{ROOM_URL}?seat=abc')
    assert response.status_code == 200
    assert _highlighted(response.get_data(as_text=True)) == []


def test_room_page_highlights_a_movable_seat_for_staff(seeded_db, login_as):
    html = login_as(1).get(f'{ROOM_URL}?seat=5').get_data(as_text=True)
    assert _highlighted(html) == [5]
    # the note is for students, who do not see the movable seats one by one
    assert 'A SEAT FROM THIS CATEGORY' not in html


def test_seat_page_tells_students_their_movable_seat_category(seeded_db, login_as):
    html = login_as(2).get('/seats/5/').get_data(as_text=True)
    assert '(YOU WILL USE A SEAT FROM THIS CATEGORY)' in html
    assert _highlighted(html) == []
