import pytest

from server.models import db, Exam, Room


@pytest.fixture
def exam169(seeded_db):
    exam = db.session.get(Exam, 1)
    assert exam is not None
    assert [room.id for room in exam.rooms] == [1]
    yield exam


def test_get_room_by_int_id(exam169):
    room = exam169.get_room(1)
    assert room is not None
    assert room.id == 1


def test_get_room_by_str_id(exam169):
    # room ids stored in student preferences are strings
    room = exam169.get_room('1')
    assert room is not None
    assert room.id == 1


def test_get_room_missing_id(exam169):
    assert exam169.get_room(999) is None


def test_get_room_deleted(exam169):
    db.session.delete(exam169.rooms[0])
    db.session.commit()
    assert exam169.get_room(1) is None


def test_get_room_from_other_exam(exam169):
    other_exam = Exam(offering_canvas_id=exam169.offering_canvas_id, name='final',
                      display_name='Final', is_active=False)
    other_room = Room(name='soda888', display_name='Soda 888')
    other_exam.rooms.append(other_room)
    db.session.add(other_exam)
    db.session.commit()

    assert exam169.get_room(other_room.id) is None
    assert other_exam.get_room(other_room.id) is other_room
