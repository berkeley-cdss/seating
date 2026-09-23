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
        return (self.wants, self.avoids, self.room_wants, self.room_avoids) == (other.wants, other.avoids, other.room_wants, other.room_avoids)  # noqa

    def __ne__(self, other):
        return not (self == other)

    def __repr__(self):
        return f'Preference(wants={self.wants}, avoids={self.avoids}, room_wants={self.room_wants}, room_avoids={self.room_avoids})'  # noqa

    def __str__(self):
        return f'Preference(wants={self.wants}, avoids={self.avoids}, room_wants={self.room_wants}, room_avoids={self.room_avoids})'  # noqa


def _seat_features(seat: Seat):
    """
    The two things a preference is matched against: the seat's lower-cased attributes and its room id.
    Computed once per seat, since assignment compares every seat against every distinct preference.
    """
    return {attr.lower() for attr in seat.attributes}, seat.room.id


def _features_match_preference(attrs: set[str], room_id, preference: Preference):
    if not all(want.lower() in attrs for want in preference.wants):
        return False
    if any(avoid.lower() in attrs for avoid in preference.avoids):
        return False
    if preference.room_wants and not any(int(a) == room_id for a in preference.room_wants):
        return False
    return all(int(a) != room_id for a in preference.room_avoids)


def is_seat_valid_for_preference(seat: Seat, preference: Preference):
    """
    Check if a seat is valid for a given preference.
    Comparison of attributes is case-insensitive.
    """
    attrs, room_id = _seat_features(seat)
    return _features_match_preference(attrs, room_id, preference)


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
    Optimized Strategy:
    1. (One-Time) Group all students by preference into lists.
    2. (One-Time) Group all seats by preference into sets for fast removal.
    3. Loop N times (once per student):
     a. Find the "most restrictive" preference by checking group lengths.
     b. Pick a random student and seat from those groups.
     c. Remove the student from their list.
     d. Remove the seat from *all* seat sets it belongs to so it can't be assigned again.
    """
    # These two properties each run a single query that also loads the assignment
    # (or lack of one) for every row. Do not iterate `exam.students` / `exam.seats`
    # and check `.assignment` here: that is one query per student and per seat.
    students = set(exam.unassigned_students)
    all_seats = set(exam.unassigned_seats)
    assignments = []

    if not students:
        return []

    # Step 1. Pre-calculate Student Groups
    students_by_pref: dict[Preference, list[Student]] = \
        arr_to_dict(students, key_getter=get_preference_from_student)

    all_preferences = students_by_pref.keys()

    # Step 2. Pre-calculate Seat Groups
    # Lower-cased attributes and room id are computed once per seat, then matched
    # against every distinct preference (seats x preferences comparisons).
    seat_features = {seat: _seat_features(seat) for seat in all_seats}
    seats_by_pref: dict[Preference, set[Seat]] = {
        preference: {seat for seat, (attrs, room_id) in seat_features.items()
                     if _features_match_preference(attrs, room_id, preference)}
        for preference in all_preferences
    }

    # Step 3. Run the Loop N times
    for i in range(len(students)):
        # Find preferences that still have students
        active_preferences = [p for p, s_list in students_by_pref.items() if s_list]

        if not active_preferences:
            # Should not happen, but good to check
            break

        # a. Find the most restrictive preference (least seats avaialable)
        min_preference: Preference = min(
            active_preferences,
            key=lambda k: len(seats_by_pref[k])
        )

        min_students: list[Student] = students_by_pref[min_preference]
        min_seats: set[Seat] = seats_by_pref[min_preference]

        if not min_seats:
            # Need to get the *original* full list of students for the error
            original_students_for_pref = arr_to_dict(
                exam.unassigned_students, get_preference_from_student
            )[min_preference]
            raise NotEnoughSeatError(exam, original_students_for_pref, min_preference)

        # b. Pick a random student and seat
        # Always convert to list in a consistent way to ensure predictable mock calls
        min_students_list = list(min_students)
        min_seats_list = list(min_seats)
        
        student = random.choice(min_students_list)
        seat = random.choice(min_seats_list)

        assignments.append(SeatAssignment(student=student, seat=seat))

        # c. Remove the student
        min_students.remove(student)

        # d. Remove the seat from *all* preference sets
        for pref_set in seats_by_pref.values():
            pref_set.discard(seat)

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
