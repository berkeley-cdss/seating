"""
Seat maps show each assigned student's photo in their seat's tooltip. The photos must load
lazily: otherwise the browser fetches one photo per assigned student as soon as a seat map
opens (1,500 requests on the assign page of a large exam), even though they stay hidden.
"""
import re

import pytest

from server.models import db, Exam, SeatAssignment, Student

EXAM_URL = '/offerings/1234567/exams/midterm1'


@pytest.fixture
def exam(seeded_db):
    exam = db.session.get(Exam, 1)
    # the seed already seats a student in a fixed seat; seat another in a movable one,
    # since the seat map draws the two kinds with separate markup
    movable_seat = next(seat for seat in exam.rooms[0].seats if seat.fixed is False)
    student = Student.query.filter_by(exam_id=exam.id, canvas_id='345678').one()
    db.session.add(SeatAssignment(student=student, seat=movable_seat))
    db.session.commit()
    yield exam


def _photo_imgs(response):
    assert response.status_code == 200
    return re.findall(r'<img class="photo"[^>]*>', response.get_data(as_text=True))


@pytest.mark.parametrize('path', [
    '/rooms/1/',
    '/students/3/assign/',
])
def test_seat_map_photos_load_lazily(exam, login_as, path):
    photos = _photo_imgs(login_as(1).get(EXAM_URL + path))
    assert len(photos) == 2  # one fixed seat, one movable seat
    for photo in photos:
        assert 'loading="lazy"' in photo


@pytest.mark.app_config(MOCK_C1C=True)
def test_photo_is_fetched_once_then_cached(seeded_db, login_as):
    from server.cache import cache_key_photo, cache_store
    sid = db.session.get(Student, 1).sid
    cache_store.delete(cache_key_photo(sid))
    response = login_as(1).get('/offerings/1234567/exams/midterm1/students/1/photo/')
    assert response.status_code == 200
    assert response.mimetype == 'image/jpeg'
    assert cache_store.get(cache_key_photo(sid)) == response.data
    cache_store.delete(cache_key_photo(sid))


PHOTO_URL = EXAM_URL + '/students/{}/photo/'


@pytest.fixture
def photo_caches(seeded_db):
    """Empty photo and roster caches, and the C1C requests made, by student id."""
    from server.cache import cache_key_photo, cache_key_roster_sids, cache_store
    sids = ['3033033334', '3033033335', '3033033336', '3033033399']

    def clear():
        cache_store.delete(cache_key_roster_sids('1234567'))
        for sid in sids:
            cache_store.delete(cache_key_photo(sid))

    clear()
    yield
    clear()


@pytest.fixture
def c1c_requests(monkeypatch):
    from server.services.c1c import C1C
    requested = []
    get_photo = C1C.get_student_photo

    def recording_get_photo(self, sid):
        requested.append(sid)
        return get_photo(self, sid)

    monkeypatch.setattr(C1C, 'get_student_photo', recording_get_photo)
    return requested


@pytest.mark.app_config(MOCK_C1C=True)
def test_photo_uses_the_student_id_from_canvas(photo_caches, c1c_requests, login_as):
    # the import gave another student id: the photo is still fetched by the one Canvas has
    student = db.session.get(Student, 1)
    student.sid = '3033033399'
    db.session.commit()
    response = login_as(1).get(PHOTO_URL.format(1))
    assert response.mimetype == 'image/jpeg'
    assert c1c_requests == ['3033033334']


@pytest.mark.app_config(MOCK_C1C=True)
def test_no_photo_for_a_student_not_on_the_canvas_roster(photo_caches, c1c_requests, login_as):
    student = db.session.get(Student, 1)
    student.canvas_id = '999999'
    db.session.commit()
    response = login_as(1).get(PHOTO_URL.format(1))
    assert response.mimetype == 'image/png'  # the placeholder
    assert c1c_requests == []


@pytest.mark.parametrize('sid', ['3033033334/../../other', '../photo', '', None, '３０３'])
def test_c1c_requests_only_all_digit_student_ids(app, monkeypatch, sid):
    from server.services.c1c import C1C
    client = C1C(None, 'https://c1c.example', 'user', 'password')
    monkeypatch.setattr(client, '_make_request', lambda path: pytest.fail(f'requested {path}'))
    with app.app_context():
        assert client.get_student_photo(sid) is None
