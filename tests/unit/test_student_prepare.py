from random import seed
from requests import head
from server.models import Seat, SeatAssignment, User, Offering, Exam, Room, Student
from server.services.core.data import prepare_students
from server.services.core.student import StudentImportConfig, room_id_to_attr
from server.typings.enum import AssignmentImportStrategy, MissingRowImportStrategy, NewRowImportStrategy, \
    UpdatedRowImportStrategy
from server.typings.exception import DataValidationError
import pytest


@pytest.fixture
def exam169(seeded_db):
    exam = Exam.query.get(1)
    assert exam is not None
    assert len(exam.students) == 3
    yield exam


JOHN = {'email': 'john.doe@example.com', 'name': 'John Doe', 'canvas id': '123456'}


def test_missing_email_in_header(exam169):
    headers = ['name', 'canvas id']
    john_with_missing_email = JOHN.copy()
    del john_with_missing_email['email']
    rows = [john_with_missing_email]
    try:
        prepare_students(exam169, headers, rows)
    except DataValidationError as e:
        assert 'email' in str(e)


def test_missing_name_in_header(exam169):
    headers = ['email', 'canvas id']
    john_with_missing_name = JOHN.copy()
    del john_with_missing_name['name']
    rows = [john_with_missing_name]
    try:
        prepare_students(exam169, headers, rows)
    except DataValidationError as e:
        assert 'name' in str(e)


def test_missing_canvas_id_in_header(exam169):
    headers = ['email', 'name']
    john_with_missing_canvas_id = JOHN.copy()
    del john_with_missing_canvas_id['canvas id']
    rows = [john_with_missing_canvas_id]
    try:
        prepare_students(exam169, headers, rows)
    except DataValidationError as e:
        assert 'canvas id' in str(e) or 'bcourses id' in str(e)


def test_one_new_student_import_default_config(exam169):
    headers = ['email', 'name', 'canvas id']
    john_copy = JOHN.copy()
    john_copy_orig = john_copy.copy()
    rows = [john_copy]
    new_students, updated_students, invalid_students, students_ids_to_remove = \
        prepare_students(exam169, headers, rows)
    assert len(new_students) == 1
    assert len(updated_students) == 0
    assert len(invalid_students) == 0
    assert len(students_ids_to_remove) == 0
    assert new_students[0].email == john_copy_orig['email']
    assert new_students[0].name == john_copy_orig['name']
    assert new_students[0].canvas_id == john_copy_orig['canvas id']


def test_one_updated_student_import_default_config(exam169):
    headers = ['email', 'name', 'canvas id']
    first_student_canvas_id = exam169.students[0].canvas_id
    john_copy = JOHN.copy()
    john_copy['canvas id'] = first_student_canvas_id
    john_copy_orig = john_copy.copy()
    rows = [john_copy]
    new_students, updated_students, invalid_students, students_ids_to_remove = \
        prepare_students(exam169, headers, rows)
    assert len(new_students) == 0
    assert len(updated_students) == 1
    assert len(invalid_students) == 0
    assert len(students_ids_to_remove) == 0
    assert updated_students[0].email == john_copy_orig['email']
    assert updated_students[0].name == john_copy_orig['name']
    assert updated_students[0].canvas_id == john_copy_orig['canvas id']


def test_one_invalid_student_import_default_config(exam169):
    headers = ['email', 'name', 'canvas id']
    john_copy = JOHN.copy()
    del john_copy['canvas id']
    rows = [john_copy]
    new_students, updated_students, invalid_students, students_ids_to_remove = \
        prepare_students(exam169, headers, rows)
    assert len(new_students) == 0
    assert len(updated_students) == 0
    assert len(invalid_students) == 1


def test_missing_student_import_strategy_delete(exam169):
    orig_students_count = len(exam169.students)
    headers = ['email', 'name', 'canvas id']
    john_copy = JOHN.copy()
    john_copy_orig = john_copy.copy()
    rows = [john_copy]
    new_students, updated_students, invalid_students, students_ids_to_remove = \
        prepare_students(exam169, headers, rows, config=StudentImportConfig(
            missing_student_import_strategy=MissingRowImportStrategy.DELETE))
    assert len(new_students) == 1
    assert len(updated_students) == 0
    assert len(invalid_students) == 0
    assert len(students_ids_to_remove) == orig_students_count
    assert new_students[0].email == john_copy_orig['email']
    assert new_students[0].name == john_copy_orig['name']
    assert new_students[0].canvas_id == john_copy_orig['canvas id']


def test_new_student_import_strategy_ignore(exam169):
    headers = ['email', 'name', 'canvas id']
    john_copy = JOHN.copy()
    rows = [john_copy]
    new_students, updated_students, invalid_students, students_ids_to_remove = \
        prepare_students(exam169, headers, rows, config=StudentImportConfig(
            new_student_import_strategy=NewRowImportStrategy.IGNORE))
    assert len(new_students) == 0
    assert len(updated_students) == 0
    assert len(invalid_students) == 1
    assert len(students_ids_to_remove) == 0


def test_update_student_preference_default_config(exam169):
    headers = ['email', 'name', 'canvas id', 'New_Want_Attr', 'New_Avoid_Attr']
    first_student_canvas_id = exam169.students[0].canvas_id
    updated_student = {
        'canvas id': first_student_canvas_id,
        'New_Want_Attr': 'true',
        'New_Avoid_Attr': 'false'
    }
    rows = [updated_student]
    new_students, updated_students, invalid_students, students_ids_to_remove = \
        prepare_students(exam169, headers, rows)
    assert len(new_students) == 0
    assert len(updated_students) == 1
    assert len(invalid_students) == 0
    assert len(students_ids_to_remove) == 0
    assert updated_students[0].wants == {'new_want_attr'}
    assert updated_students[0].avoids == {'new_avoid_attr'}


def test_update_student_preference_with_room_default_config(exam169):
    headers = ['email', 'name', 'canvas id', 'Room:1']
    first_student_canvas_id = exam169.students[0].canvas_id
    updated_student = {
        'canvas id': first_student_canvas_id,
        'room:1': 'true'
    }
    rows = [updated_student]
    new_students, updated_students, invalid_students, students_ids_to_remove = \
        prepare_students(exam169, headers, rows)
    assert len(new_students) == 0
    assert len(updated_students) == 1
    assert len(invalid_students) == 0
    assert len(students_ids_to_remove) == 0
    assert updated_students[0].wants == set()
    assert updated_students[0].avoids == set()
    assert updated_students[0].room_wants == {'1'}
    assert updated_students[0].room_avoids == set()


def test_update_student_preference_merge(seeded_db, exam169):
    headers = ['email', 'name', 'canvas id', 'New_Want_Attr', 'New_Avoid_Attr']
    first_student = exam169.students[0]
    first_student.wants = {'old_want_attr'}
    first_student.avoids = {'old_avoid_attr'}
    old_room_wants = first_student.room_wants
    old_room_avoids = first_student.room_avoids
    seeded_db.session.commit()
    first_student_canvas_id = first_student.canvas_id
    updated_student = {
        'canvas id': first_student_canvas_id,
        'New_Want_Attr': 'true',
        'New_Avoid_Attr': 'false'
    }
    rows = [updated_student]
    new_students, updated_students, invalid_students, students_ids_to_remove = \
        prepare_students(exam169, headers, rows,
                         config=StudentImportConfig(updated_preference_import_strategy=UpdatedRowImportStrategy.MERGE))
    assert len(new_students) == 0
    assert len(updated_students) == 1
    assert len(invalid_students) == 0
    assert len(students_ids_to_remove) == 0
    assert updated_students[0].wants == {'old_want_attr', 'new_want_attr'}
    assert updated_students[0].avoids == {'old_avoid_attr', 'new_avoid_attr'}
    assert updated_students[0].room_wants == old_room_wants
    assert updated_students[0].room_avoids == old_room_avoids


def test_update_student_preference_merge_conflict(seeded_db, exam169):
    headers = ['email', 'name', 'canvas id', 'old_want_attr',]
    first_student = exam169.students[0]
    first_student.wants = {'old_want_attr'}
    seeded_db.session.commit()
    first_student_canvas_id = first_student.canvas_id
    updated_student = {
        'canvas id': first_student_canvas_id,
        'old_want_attr': 'false',
    }
    rows = [updated_student]
    new_students, updated_students, invalid_students, students_ids_to_remove = \
        prepare_students(exam169, headers, rows,
                         config=StudentImportConfig(updated_preference_import_strategy=UpdatedRowImportStrategy.MERGE))
    assert len(new_students) == 0
    assert len(updated_students) == 0
    assert len(invalid_students) == 1
    assert len(students_ids_to_remove) == 0


def test_update_student_preference_ignore(exam169):
    headers = ['email', 'name', 'canvas id', 'New_Want_Attr', 'New_Avoid_Attr']
    first_student = exam169.students[0]
    old_wants = first_student.wants
    old_avoids = first_student.avoids
    old_room_wants = first_student.room_wants
    old_room_avoids = first_student.room_avoids
    first_student_canvas_id = first_student.canvas_id
    updated_student = {
        'canvas id': first_student_canvas_id,
        'New_Want_Attr': 'true',
        'New_Avoid_Attr': 'false'
    }
    rows = [updated_student]
    new_students, updated_students, invalid_students, students_ids_to_remove = \
        prepare_students(exam169, headers, rows,
                         config=StudentImportConfig(updated_preference_import_strategy=UpdatedRowImportStrategy.IGNORE))
    assert len(new_students) == 0
    assert len(updated_students) == 1
    assert len(invalid_students) == 0
    assert len(students_ids_to_remove) == 0
    assert updated_students[0].wants == old_wants
    assert updated_students[0].avoids == old_avoids
    assert updated_students[0].room_wants == old_room_wants
    assert updated_students[0].room_avoids == old_room_avoids


def test_update_student_info_default_config(exam169):
    headers = ['email', 'name', 'canvas id']
    first_student = exam169.students[0]
    orig_name = first_student.name
    new_email = 'new@example.com'
    updated_student = {
        'canvas id': first_student.canvas_id,
        'email': new_email,
        'name': '',
    }
    rows = [updated_student]
    new_students, updated_students, invalid_students, students_ids_to_remove = \
        prepare_students(exam169, headers, rows)
    assert len(new_students) == 0
    assert len(updated_students) == 1
    assert len(invalid_students) == 0
    assert len(students_ids_to_remove) == 0
    assert updated_students[0].email == new_email
    assert updated_students[0].name == orig_name


def test_update_student_info_overwrite(exam169):
    headers = ['email', 'name', 'canvas id']
    first_student = exam169.students[0]
    updated_student = {
        'canvas id': first_student.canvas_id,
        'email': '',
        'name': '',
    }
    rows = [updated_student]
    new_students, updated_students, invalid_students, students_ids_to_remove = \
        prepare_students(exam169, headers, rows,
                         config=StudentImportConfig(updated_student_info_import_strategy=UpdatedRowImportStrategy.OVERWRITE))
    assert len(new_students) == 0
    assert len(updated_students) == 0
    # since it is forced to overwrite, email would be set to blank, and thus it is not invalid
    assert len(invalid_students) == 1
    assert len(students_ids_to_remove) == 0


def test_update_student_info_ignore(exam169):
    headers = ['email', 'name', 'canvas id']
    first_student = exam169.students[0]
    orig_name, orig_email = first_student.name, first_student.email
    john = JOHN.copy()
    john['canvas id'] = first_student.canvas_id
    rows = [john]
    new_students, updated_students, invalid_students, students_ids_to_remove = \
        prepare_students(exam169, headers, rows,
                         config=StudentImportConfig(updated_student_info_import_strategy=UpdatedRowImportStrategy.IGNORE))
    assert len(new_students) == 0
    assert len(updated_students) == 1
    assert len(invalid_students) == 0
    assert len(students_ids_to_remove) == 0
    assert updated_students[0].email == orig_email
    assert updated_students[0].name == orig_name


def test_update_student_assignment_default_config(seeded_db, exam169):
    headers = ['email', 'name', 'canvas id', 'seat id']
    first_student = exam169.students[0]
    first_student.wants = set()
    first_student.avoids = set()
    first_student.room_wants = set()
    first_student.room_avoids = set()
    seeded_db.session.commit()
    first_student_canvas_id = first_student.canvas_id
    some_seats = exam169.unassigned_seats
    first_seat = some_seats[0]
    updated_student = {
        'canvas id': first_student_canvas_id,
        'seat id': first_seat.id
    }
    rows = [updated_student]
    new_students, updated_students, invalid_students, students_ids_to_remove = \
        prepare_students(exam169, headers, rows)
    assert len(new_students) == 0
    assert len(updated_students) == 1
    assert len(invalid_students) == 0
    assert len(students_ids_to_remove) == 0
    assert updated_students[0].assignment.seat.id == first_seat.id
    assert not updated_students[0].assignment.emailed


def test_update_student_assignment_default_config_emailed(seeded_db, exam169):
    headers = ['email', 'name', 'canvas id', 'seat id']
    first_student = exam169.students[0]
    first_student.wants = set()
    first_student.avoids = set()
    first_student.room_wants = set()
    first_student.room_avoids = set()
    seeded_db.session.commit()
    first_student_canvas_id = first_student.canvas_id
    some_seats = exam169.unassigned_seats
    first_seat = some_seats[0]
    updated_student = {
        'canvas id': first_student_canvas_id,
        'seat id': first_seat.id,
        'emailed': 'true'
    }
    rows = [updated_student]
    new_students, updated_students, invalid_students, students_ids_to_remove = \
        prepare_students(exam169, headers, rows)
    assert len(new_students) == 0
    assert len(updated_students) == 1
    assert len(invalid_students) == 0
    assert len(students_ids_to_remove) == 0
    assert updated_students[0].assignment.seat.id == first_seat.id
    assert updated_students[0].assignment.emailed


def test_update_student_assignment_default_config_with_room_and_seat_name(seeded_db, exam169):
    headers = ['email', 'name', 'canvas id', 'room name', 'seat name']
    first_student = exam169.students[0]
    first_student.wants = set()
    first_student.avoids = set()
    first_student.room_wants = set()
    first_student.room_avoids = set()
    seeded_db.session.commit()
    first_student_canvas_id = first_student.canvas_id
    first_seat = list(filter(lambda s: s.fixed, exam169.unassigned_seats))[0]
    room_name = first_seat.room.name_and_start_at_time_display()
    seat_name = first_seat.name
    updated_student = {
        'canvas id': first_student_canvas_id,
        'room name': room_name,
        'seat name': seat_name
    }
    rows = [updated_student]
    new_students, updated_students, invalid_students, students_ids_to_remove = \
        prepare_students(exam169, headers, rows)
    assert len(new_students) == 0
    assert len(updated_students) == 1
    assert len(invalid_students) == 0
    assert len(students_ids_to_remove) == 0
    assert updated_students[0].assignment.seat.id == first_seat.id
    assert not updated_students[0].assignment.emailed


def test_update_student_assignment_default_config_with_room_and_seat_name_for_movable_seats(seeded_db, exam169):
    headers = ['email', 'name', 'canvas id', 'room name', 'seat name']
    first_student = exam169.students[0]
    first_student.wants = set()
    first_student.avoids = set()
    first_student.room_wants = set()
    first_student.room_avoids = set()
    seeded_db.session.commit()
    first_student_canvas_id = first_student.canvas_id
    first_seat = list(filter(lambda s: not s.fixed, exam169.unassigned_seats))[0]
    room_name = first_seat.room.name_and_start_at_time_display()
    seat_name = first_seat.name
    updated_student = {
        'canvas id': first_student_canvas_id,
        'room name': room_name,
        'seat name': seat_name
    }
    rows = [updated_student]
    new_students, updated_students, invalid_students, students_ids_to_remove = \
        prepare_students(exam169, headers, rows)
    assert len(new_students) == 0
    assert len(updated_students) == 1
    assert len(invalid_students) == 0
    assert len(students_ids_to_remove) == 0
    assert updated_students[0].assignment.seat.attributes == first_seat.attributes
    assert not updated_students[0].assignment.emailed


def test_update_student_assignment_ignore(seeded_db, exam169):
    headers = ['email', 'name', 'canvas id', 'room name', 'seat name']
    first_student = exam169.students[0]
    first_student.wants = set()
    first_student.avoids = set()
    first_student.room_wants = set()
    first_student.room_avoids = set()
    some_seats = exam169.unassigned_seats
    first_seat = some_seats[0]
    second_seat = some_seats[1]
    first_student.assignment = SeatAssignment(student=first_student, seat=first_seat, emailed=True)
    seeded_db.session.commit()
    first_student_canvas_id = first_student.canvas_id
    that_student = Student.query.get(first_student.id)
    assert that_student.assignment.seat.id == first_seat.id
    updated_student = {
        'canvas id': first_student_canvas_id,
        'seat id': second_seat.id
    }
    rows = [updated_student]
    new_students, updated_students, invalid_students, students_ids_to_remove = \
        prepare_students(exam169, headers, rows,
                         config=StudentImportConfig(assignment_import_strategy=AssignmentImportStrategy.IGNORE))
    assert len(new_students) == 0
    assert len(updated_students) == 1
    assert len(invalid_students) == 0
    assert len(students_ids_to_remove) == 0
    assert updated_students[0].assignment.seat.id == first_seat.id
    assert updated_students[0].assignment.emailed


def test_update_student_assignment_reject_invalid_seat(seeded_db, exam169):
    headers = ['email', 'name', 'canvas id', 'room name', 'seat name']
    first_student = exam169.students[0]
    first_seat = exam169.unassigned_seats[0]
    first_student.room_avoids = {str(first_seat.room.id)}
    first_student.assignment = None
    seeded_db.session.commit()
    first_student_canvas_id = first_student.canvas_id
    updated_student = {
        'canvas id': first_student_canvas_id,
        'seat id': first_seat.id
    }
    rows = [updated_student]
    # don't overwrite the original preferences; we need that to make a conflict
    new_students, updated_students, invalid_students, students_ids_to_remove = \
        prepare_students(exam169, headers, rows,
                         config=StudentImportConfig(updated_preference_import_strategy=UpdatedRowImportStrategy.IGNORE))
    assert len(new_students) == 0
    assert len(updated_students) == 1
    assert len(invalid_students) == 0
    assert len(students_ids_to_remove) == 0
    assert updated_students[0].assignment is None


def test_update_student_assignment_force_invalid_seat(seeded_db, exam169):
    headers = ['email', 'name', 'canvas id', 'room name', 'seat name']
    first_student = exam169.students[0]
    first_seat = exam169.unassigned_seats[0]
    first_student.room_avoids = {str(first_seat.room.id)}
    first_student.assignment = None
    seeded_db.session.commit()
    first_student_canvas_id = first_student.canvas_id
    updated_student = {
        'canvas id': first_student_canvas_id,
        'seat id': first_seat.id
    }
    rows = [updated_student]
    # don't overwrite the original preferences; we need that to make a conflict
    new_students, updated_students, invalid_students, students_ids_to_remove = \
        prepare_students(exam169, headers, rows,
                         config=StudentImportConfig(updated_preference_import_strategy=UpdatedRowImportStrategy.IGNORE,
                                                    assignment_import_strategy=AssignmentImportStrategy.FORCE))

    assert len(new_students) == 0
    assert len(updated_students) == 1
    assert len(invalid_students) == 0
    assert len(students_ids_to_remove) == 0
    assert updated_students[0].assignment.seat.id == first_seat.id


def test_revalidate_existing_assignments_to_weed_out_existing_conflicts(seeded_db, exam169):
    first_student = exam169.students[0]
    first_seat = exam169.unassigned_seats[0]
    first_student.assignment = SeatAssignment(student=first_student, seat=first_seat)
    first_student.room_avoids = {str(first_seat.room.id)}
    seeded_db.session.commit()
    first_student_canvas_id = first_student.canvas_id
    headers = ['email', 'name', 'canvas id']
    updated_student = {
        'canvas id': first_student_canvas_id,
    }
    rows = [updated_student]
    # keep original preferences; we need that to make a conflict
    new_students, updated_students, invalid_students, students_ids_to_remove = \
        prepare_students(exam169, headers, rows,
                         config=StudentImportConfig(updated_preference_import_strategy=UpdatedRowImportStrategy.MERGE))
    assert len(new_students) == 0
    assert len(updated_students) == 1
    assert len(invalid_students) == 0
    assert len(students_ids_to_remove) == 0
    assert updated_students[0].room_avoids == {str(first_seat.room.id)}
    assert updated_students[0].assignment is None


def test_revalidate_existing_assignments_while_changing_prefs(seeded_db, exam169):
    first_student = exam169.students[0]
    first_seat = exam169.unassigned_seats[0]
    first_student.assignment = SeatAssignment(student=first_student, seat=first_seat)
    seeded_db.session.commit()
    headers = ['email', 'name', 'canvas id', room_id_to_attr(first_seat.room.id)]
    first_student_canvas_id = exam169.students[0].canvas_id
    updated_student = {
        'canvas id': first_student_canvas_id,
        room_id_to_attr(first_seat.room.id): 'false'
    }
    rows = [updated_student]
    new_students, updated_students, invalid_students, students_ids_to_remove = \
        prepare_students(exam169, headers, rows)
    assert len(new_students) == 0
    assert len(updated_students) == 1
    assert len(invalid_students) == 0
    assert len(students_ids_to_remove) == 0
    assert updated_students[0].room_avoids == {str(first_seat.room.id)}
    assert updated_students[0].assignment is None


def test_no_revalidate_exisiting_assignments_while_giving_conflicting_prefs(seeded_db, exam169):
    first_student = exam169.students[0]
    first_seat = exam169.unassigned_seats[0]
    first_student.assignment = SeatAssignment(student=first_student, seat=first_seat)
    seeded_db.session.commit()
    headers = ['email', 'name', 'canvas id', room_id_to_attr(first_seat.room.id)]
    first_student_canvas_id = exam169.students[0].canvas_id
    updated_student = {
        'canvas id': first_student_canvas_id,
        room_id_to_attr(first_seat.room.id): 'false'
    }
    rows = [updated_student]
    new_students, updated_students, invalid_students, students_ids_to_remove = \
        prepare_students(exam169, headers, rows,
                         config=StudentImportConfig(revalidate_existing_assignments=False))
    assert len(new_students) == 0
    assert len(updated_students) == 1
    assert len(invalid_students) == 0
    assert len(students_ids_to_remove) == 0
    assert updated_students[0].room_avoids == {str(first_seat.room.id)}
    assert updated_students[0].assignment.seat.id == first_seat.id
