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
    '/students/456789/assign/',
])
def test_seat_map_photos_load_lazily(exam, login_as, path):
    photos = _photo_imgs(login_as(1).get(EXAM_URL + path))
    assert len(photos) == 2  # one fixed seat, one movable seat
    for photo in photos:
        assert 'loading="lazy"' in photo
