import random

from server.models import Seat, SeatAssignment, Student
from server.typings.exception import NotEnoughSeatError, SeatOverrideError
from server.utils.misc import arr_to_dict


class Preference:
    def __init__(self, wants: set[str], avoids: set[str], room_wants: set[str], room_avoids: set[str]):
        self.wants = wants
        self.avoids = avoids
        self.room_wants = room_wants
        self.room_avoids = room_avoids

    def __hash__(self):
        return hash((frozenset(self.wants), frozenset(self.avoids), frozenset(self.room_wants), frozenset(self.room_avoids)))

    def __eq__(self, other):
        return (self.wants, self.avoids, self.room_wants, self.room_avoids) == (other.wants, other.avoids, other.room_wants, other.room_avoids)

    def __ne__(self, other):
        return not (self == other)

    def __repr__(self):
        return f'Preference(wants={self.wants}, avoids={self.avoids}, room_wants={self.room_wants}, room_avoids={self.room_avoids})'

    def __str__(self):
        return f'Preference(wants={self.wants}, avoids={self.avoids}, room_wants={self.room_wants}, room_avoids={self.room_avoids})'


def is_seat_valid_for_preference(seat: Seat, preference: Preference):
    """
    Check if a seat is valid for a given preference.
    Comparison of attributes is case-insensitive.
    """
    wants, avoids, room_wants, room_avoids = preference.wants, preference.avoids, preference.room_wants, preference.room_avoids
    return (all(want.lower() in {attr.lower() for attr in seat.attributes} for want in wants) and  # noqa
            all(avoid.lower() not in {attr.lower() for attr in seat.attributes} for avoid in avoids) and  # noqa
            (not room_wants or any(int(a) == seat.room.id for a in room_wants)) and  # noqa
            all(int(a) != seat.room.id for a in room_avoids)
            )


def filter_seats_by_preference(seats, preference: Preference):
    """
    Return seats available for a given preference.
    Comparison of attributes is case-insensitive.
    """
    return [seat for seat in seats if is_seat_valid_for_preference(seat, preference)]


def get_preference_from_student(student):
    return Preference(student.wants, student.avoids, student.room_wants, student.room_avoids)


def assign_students(exam):
    """
    The strategy:
    Look for students whose requirements are the most restrictive
        (i.e. have the fewest possible seats).
    Randomly assign them a seat.
    Repeat.
    """
    students = set(exam.unassigned_students)
    seats = set(exam.unassigned_seats)

    assignments = []
    while students:
        students_by_preference: dict[Preference, list[Student]] = \
            arr_to_dict(students, key_getter=get_preference_from_student)
        seats_by_preference: dict[Preference, list[Seat]] = {
            preference: filter_seats_by_preference(seats, preference)
            for preference in students_by_preference.keys()
        }
        min_preference: Preference = min(seats_by_preference,
                                         key=lambda k: len(seats_by_preference[k]))
        min_students: list[Student] = students_by_preference[min_preference]
        min_seats: list[Seat] = seats_by_preference[min_preference]

        if not min_seats:
            raise NotEnoughSeatError(exam, min_students, min_preference)

        student = random.choice(min_students)
        seat = random.choice(min_seats)

        students.remove(student)
        seats.remove(seat)

        assignments.append(SeatAssignment(student=student, seat=seat))
    return assignments


def assign_single_student(exam, student, seat=None, ignore_restrictions=False):
    """
    Assign a single student to a seat.
    If a seat is not provided, try to find a seat that meets the student's requirements (if ignore_restrictions is False),
    or just any seat that is available (if ignore_restrictions is True).
    If a seat is provided, check if the seat is available and meets the student's requirements (if ignore_restrictions is False),
    or only check if the seat is available (if ignore_restrictions is True).
    Then, the chosen seat is assigned to the student.

    The original assignment will NOT be removed! It is the caller's responsibility to remove the original assignment if needed.
    """
    preference: Preference = get_preference_from_student(student)
    seats: list[Seat] = filter_seats_by_preference(exam.unassigned_seats, preference) \
        if not ignore_restrictions else exam.unassigned_seats

    # if a seat is provided, check it
    if seat and seat not in seats:
        raise SeatOverrideError(student, seat,
                                "Seat is already taken or does exist in the exam, or does not meet the student's requirements.")

    # if seat is not provided, try getting a seat that meets the student's requirements
    if not seat:
        if not seats:
            raise NotEnoughSeatError(exam, [student], preference)
        seat = random.choice(seats)

    # create and return a new assignment
    return SeatAssignment(student=student, seat=seat)
