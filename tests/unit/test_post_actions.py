"""
Deleting an exam, a room or a student, toggling an exam and hiding an offering change data, so they
take only POST, with the session's CSRF token: a link or form on another site can't make them.
"""
import re

import pytest

from server.models import db, Exam, Offering, Room, Student

OFFERING_URL = '/offerings/1234567/'
EXAM_URL = '/offerings/1234567/exams/midterm1'


def _csrf_token(page):
    return re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', page).group(1)


def _room_id():
    return Room.query.filter_by(exam_id=1).order_by(Room.id).first().id


def _unchanged(action, url):
    """Whether the data `action`, posted to `url`, would change is as the seed left it."""
    return {
        'hide': lambda: not Offering.query.filter_by(canvas_id='1234567').one().is_hidden,
        'delete exam': lambda: db.session.get(Exam, 1) is not None,
        'toggle exam': lambda: not db.session.get(Exam, 1).is_active,
        'delete room': lambda: db.session.get(Room, int(url.rsplit('/', 2)[1])) is not None,
        'delete student': lambda: db.session.get(Student, 1) is not None,
    }[action]()


ACTIONS = {
    'hide': lambda: f'{OFFERING_URL}hide/',
    'delete exam': lambda: f'{EXAM_URL}/delete/',
    'toggle exam': lambda: f'{EXAM_URL}/toggle/',
    'delete room': lambda: f'{EXAM_URL}/rooms/{_room_id()}/delete',
    'delete student': lambda: f'{EXAM_URL}/students/1/delete',
}


@pytest.fixture
def staff(seeded_db, login_as):
    # the seed exam starts inactive, so toggling it has a change to make
    db.session.get(Exam, 1).is_active = False
    db.session.add(Exam(offering_canvas_id='1234567', name='final', display_name='Final', is_active=True))
    db.session.commit()
    return login_as(1)


@pytest.mark.parametrize('action', ACTIONS)
def test_following_a_link_changes_nothing(staff, action):
    url = ACTIONS[action]()
    assert staff.get(url).status_code == 405
    db.session.expire_all()
    assert _unchanged(action, url)


@pytest.mark.parametrize('action', ACTIONS)
def test_posting_without_the_csrf_token_changes_nothing(staff, action):
    url = ACTIONS[action]()
    response = staff.post(url, follow_redirects=True)
    assert 'The CSRF token is missing.' in response.get_data(as_text=True)
    db.session.expire_all()
    assert _unchanged(action, url)


@pytest.mark.parametrize('action', ACTIONS)
def test_posting_with_the_csrf_token_makes_the_change(staff, action):
    page = staff.get(f'{EXAM_URL}/students/').get_data(as_text=True)
    url = ACTIONS[action]()
    assert staff.post(url, data={'csrf_token': _csrf_token(page)}).status_code == 302
    db.session.expire_all()
    assert not _unchanged(action, url)


@pytest.mark.parametrize('page_url, action', [
    ('/offerings', 'hide'),
    (OFFERING_URL, 'delete exam'),
    (OFFERING_URL, 'toggle exam'),
    (f'{EXAM_URL}/', 'delete room'),
    (f'{EXAM_URL}/students/', 'delete student'),
])
def test_buttons_post_with_the_csrf_token(staff, page_url, action):
    page = staff.get(page_url).get_data(as_text=True)
    url = ACTIONS[action]()
    form = re.search(rf'<form method="POST" action="{re.escape(url)}"[^>]*>\s*<input name="csrf_token"', page)
    assert form, f'no form posting to {url} with a CSRF token on {page_url}'


def test_a_rejected_post_does_not_redirect_to_another_site(staff):
    response = staff.post(f'{EXAM_URL}/delete/', headers={'Referer': 'https://example.com/'})
    assert response.status_code == 302
    assert 'example.com' not in response.location


def test_a_rejected_fetch_gets_json(staff):
    response = staff.post(f'{EXAM_URL}/students/email/preview/', headers={'Accept': 'application/json'})
    assert response.status_code == 400
    assert 'csrf_token' in response.get_json()['errors']
