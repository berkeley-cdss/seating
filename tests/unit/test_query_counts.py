"""
Guards against N+1 query regressions on the hot paths.

Each of these used to issue one (or more) queries per student and/or per seat.
The bounds below are deliberately loose constants: they must not scale with the
number of students or seats in the fixtures.
"""
import contextlib

import pytest
from sqlalchemy import event

from server.models import Exam, Seat, SeatAssignment, Student, db
from server.services.core.assign import assign_students
from server.services.core.export import export_exam_student_info
from server.services.core.student import StudentImportConfig, prepare_students


@contextlib.contextmanager
def count_queries():
    counter = {'n': 0}

    def _before(conn, cursor, statement, params, context, executemany):
        counter['n'] += 1

    event.listen(db.engine, 'before_cursor_execute', _before)
    try:
        yield counter
    finally:
        event.remove(db.engine, 'before_cursor_execute', _before)


@pytest.fixture
def exam(seeded_db):
    # start from a clean identity map so nothing seeded is already cached in the session
    seeded_db.session.expunge_all()
    exam = Exam.query.get(1)
    assert exam is not None
    return exam


def test_unassigned_students_and_seats_are_constant_queries(exam, seeded_db):
    with count_queries() as c:
        students = exam.unassigned_students
        seats = exam.unassigned_seats
    assert c['n'] <= 3, c['n']
    # the seeded exam has 3 students with 1 assignment, and 7 seats with 1 taken
    assert len(students) == 2
    assert len(seats) == 6
    # results are usable without further queries
    with count_queries() as c:
        assert all(s.assignment is None for s in students)
        assert all(s.assignment is None and s.room is not None for s in seats)
    assert c['n'] == 0


def test_assign_students_is_constant_queries(exam, seeded_db):
    with count_queries() as c:
        assignments = assign_students(exam)
    assert c['n'] <= 4, c['n']
    assert len(assignments) == 2
    seeded_db.session.add_all(assignments)
    with count_queries() as c:
        seeded_db.session.commit()
    # the whole batch is inserted with one statement
    assert c['n'] <= 2, c['n']
    assert SeatAssignment.query.count() == 3


def test_students_with_seat_is_one_query(exam, seeded_db):
    with count_queries() as c:
        students = exam.get_students(with_seat=True)
        for student in students:
            if student.assignment:
                _ = student.assignment.seat.room.display_name
    assert c['n'] == 1, c['n']
    assert len(students) == 3


def test_export_is_constant_queries(exam, seeded_db, app):
    with app.test_request_context('/'):
        with count_queries() as c:
            csv = export_exam_student_info(exam)
    assert c['n'] <= 2, c['n']
    assert csv.count('\n') >= 3


def test_prepare_students_is_constant_queries(exam, seeded_db):
    headers = ['email', 'name', 'canvas id', 'seat id']
    free_seat_ids = [seat.id for seat in exam.unassigned_seats]
    rows = [
        {'email': s.email, 'name': s.name, 'canvas id': s.canvas_id, 'seat id': str(seat_id)}
        for s, seat_id in zip(exam.students, free_seat_ids)
    ]
    rows.append({'email': 'new@berkeley.edu', 'name': 'New, Student', 'canvas id': '999999',
                 'seat id': str(free_seat_ids[-1])})
    with count_queries() as c:
        new_students, updated_students, invalid_students, to_remove = prepare_students(
            exam, headers, rows, config=StudentImportConfig())
    # a handful of up-front loads, never one per row
    assert c['n'] <= 5, c['n']
    assert len(new_students) == 1
    assert len(updated_students) == 3
    assert not invalid_students and not to_remove
    seeded_db.session.rollback()


def test_get_room_uses_loaded_rooms(exam, seeded_db):
    room = exam.rooms[0]
    with count_queries() as c:
        assert exam.get_room(room.id) is room
        assert exam.get_room(str(room.id)) is room
        assert exam.get_room(999999) is None
    assert c['n'] == 0
