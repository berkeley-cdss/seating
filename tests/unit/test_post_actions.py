"""
Deleting an exam, a room or a student, toggling an exam, hiding an offering and logging out take only
POST, and a post that another site made a signed-in browser send is refused (as in sections).
"""
import re

import pytest

from server.models import db, Exam, Offering, Room, Student

OFFERING_URL = '/offerings/1234567/'
EXAM_URL = '/offerings/1234567/exams/midterm1'
# the test client's requests go to http://localhost
SAME_ORIGIN = 'http://localhost'
# same site, were the app served from a berkeley.edu subdomain, so SameSite=Lax cookies are sent
OTHER_SUBDOMAIN = 'https://evil.berkeley.edu'


def _room_id():
    return Room.query.filter_by(exam_id=1).order_by(Room.id).first().id


def _unchanged(action, url):
    """Whether what posting `action` to `url` would change is still as the seed left it."""
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


@pytest.mark.parametrize('headers', [
    {'Sec-Fetch-Site': 'same-site', 'Origin': OTHER_SUBDOMAIN},
    {'Sec-Fetch-Site': 'cross-site', 'Origin': 'https://evil.example'},
    # browsers that send Origin but not Sec-Fetch-Site
    {'Origin': OTHER_SUBDOMAIN},
    {'Origin': 'https://localhost'},  # another scheme is another origin
    {'Origin': 'null'},  # e.g. from a sandboxed iframe
])
@pytest.mark.parametrize('action', ACTIONS)
def test_posts_from_another_site_are_refused(staff, action, headers):
    url = ACTIONS[action]()
    response = staff.post(url, headers=headers)
    assert response.status_code == 403
    assert 'came from another website' in response.get_data(as_text=True)
    db.session.expire_all()
    assert _unchanged(action, url)


@pytest.mark.parametrize('headers', [
    {'Sec-Fetch-Site': 'same-origin', 'Origin': SAME_ORIGIN},
    {'Origin': SAME_ORIGIN},  # browsers that don't send Sec-Fetch-Site
    # Sec-Fetch-Site decides when it's sent; "none" is a request the user made directly
    {'Sec-Fetch-Site': 'same-origin', 'Origin': 'https://evil.example'},
    {'Sec-Fetch-Site': 'none'},
    {},  # not from a browser, so there's no borrowed cookie
])
@pytest.mark.parametrize('action', ACTIONS)
def test_posts_from_this_app_make_the_change(staff, action, headers):
    url = ACTIONS[action]()
    assert staff.post(url, headers=headers).status_code == 302
    db.session.expire_all()
    assert not _unchanged(action, url)


def test_origin_matches_behind_cloud_run(staff):
    # Cloud Run terminates TLS and says so in X-Forwarded-Proto, which ProxyFix trusts, so a browser
    # without Sec-Fetch-Site sends an https Origin to what Flask sees as an http request
    response = staff.post(f'{EXAM_URL}/delete/', headers={'X-Forwarded-Proto': 'https', 'Origin': 'https://localhost'})
    assert response.status_code == 302
    assert db.session.get(Exam, 1) is None


def test_gets_from_another_site_are_not_refused(staff):
    # links from other sites, e.g. Canvas's redirect back after login, are GETs
    response = staff.get('/offerings', headers={'Sec-Fetch-Site': 'cross-site', 'Origin': 'https://evil.example'})
    assert response.status_code == 200


@pytest.mark.parametrize('page_url, action', [
    ('/offerings', 'hide'),
    (OFFERING_URL, 'delete exam'),
    (OFFERING_URL, 'toggle exam'),
    (f'{EXAM_URL}/', 'delete room'),
    (f'{EXAM_URL}/students/', 'delete student'),
])
def test_buttons_post(staff, page_url, action):
    page = staff.get(page_url).get_data(as_text=True)
    url = ACTIONS[action]()
    assert re.search(rf'<form method="POST" action="{re.escape(url)}"', page), \
        f'no form posting to {url} on {page_url}'


FORGED = {'Sec-Fetch-Site': 'same-site', 'Origin': OTHER_SUBDOMAIN}


@pytest.mark.parametrize('url', [
    # forms with their own CSRF token are refused all the same
    f'{EXAM_URL}/edit/',
    '/offerings/new',
    f'{EXAM_URL}/students/remove_deleted_rooms/',
    '/dev_login/',
])
def test_other_posts_from_another_site_are_refused(staff, url):
    response = staff.post(url, data={'display_name': 'Renamed', 'user_id': '123456'}, headers=FORGED)
    assert response.status_code == 403
    db.session.expire_all()
    assert db.session.get(Exam, 1).display_name == 'Midterm 1'


def test_other_sites_cannot_log_users_out(staff):
    assert staff.get('/logout/').status_code == 405
    assert staff.post('/logout/', headers=FORGED).status_code == 403
    # still signed in
    assert staff.get('/offerings').status_code == 200
    assert staff.post('/logout/', headers={'Sec-Fetch-Site': 'same-origin'}).status_code == 302
    assert staff.get('/offerings').status_code == 302


def _after_login(client):
    with client.session_transaction() as session:
        return session.get('after_login')


@pytest.mark.parametrize('action', ACTIONS)
def test_pressing_a_button_once_signed_out_returns_to_the_home_page(seeded_db, client, action):
    # e.g. the page was left open past the idle limit: signing in again must not come back to a
    # GET of a POST-only url, which would be a 405
    url = ACTIONS[action]()
    response = client.post(url, headers={'Sec-Fetch-Site': 'same-origin'})
    assert response.status_code == 302
    assert response.location.endswith('/login/')
    assert _after_login(client) is None


def test_opening_a_page_once_signed_out_returns_to_it(seeded_db, client):
    response = client.get(f'{EXAM_URL}/students/')
    assert response.location.endswith('/login/')
    assert _after_login(client) == f'http://localhost{EXAM_URL}/students/'
