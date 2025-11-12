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


def is_seat_valid_for_preference(seat: Seat, preference: Preference):
    """
    Check if a seat is valid for a given preference.
    Comparison of attributes is case-insensitive.
    """
    wants, avoids, room_wants, room_avoids = preference.wants, preference.avoids, preference.room_wants, preference.room_avoids
    return (all(want.lower() in {attr.lower() for attr in seat.attributes} for want in wants) and  # noqa
            all(avoid.lower() not in {attr.lower() for attr in seat.attributes} for avoid in avoids) and  # noqa
            (not room_wants or any(int(a) == seat.room.id for a in room_wants)) and  # noqa
            all(int(a) != seat.room.id for a in room_avoids)  # noqa
            )


def filter_seats_by_preference(seats, preference: Preference):
    """
    Return seats available for a given preference.
    Comparison of attributes is case-insensitive.
    """
    return [seat for seat in seats if is_seat_valid_for_preference(seat, preference)]


def get_preference_from_student(student):
    return Preference(student.wants, student.avoids, student.room_wants, student.room_avoids)

def assign_students(exam, max_attempts=500):
    """
    Optimized Strategy with Randomized Retries:
    1. Pre-calculate student and seat groups.
    2. Try to assign all students.
    3. If a NotEnoughSeatError occurs, it means the random choices 
       led to a "stolen seat" dead-end.
    4. We "reset" and try the whole process again, up to max_attempts.
    """
    
    # Get the "master list" of students and seats
    master_students = list(exam.unassigned_students)
    master_seats = set(exam.unassigned_seats)

    if not master_students:
        return []

    # --- Pre-calculate Student Groups (do this only ONCE) ---
    students_by_pref: dict[Preference, list[Student]] = \
        arr_to_dict(master_students, key_getter=get_preference_from_student)
    
    all_preferences = students_by_pref.keys()

    # --- Pre-calculate Seat Groups (do this only ONCE) ---
    seats_by_pref_master: dict[Preference, set[Seat]] = {
        preference: set(filter_seats_by_preference(master_seats, preference))
        for preference in all_preferences
    }

    # --- Pre-Check for "Hard Fails" (Impossible Situations) ---
    for preference, student_list in students_by_pref.items():
        num_students = len(student_list)
        num_seats = len(seats_by_pref_master[preference])
        
        if num_students > num_seats:
            # This is a "Hard Fail". No retries will ever fix this.
            # We can raise the error immediately with the correct students.
            original_students_for_pref = arr_to_dict(
                exam.unassigned_students, get_preference_from_student
            )[preference]
            
            # (Optional) Print a more specific error for your log
            print(
                f"FATAL: Preference group has {num_students} students "
                f"but only {num_seats} total matching seats available."
            )
            print(f"Preference: {preference}")
            print(f"Students: {original_students_for_pref}")
            
            raise NotEnoughSeatError(exam, original_students_for_pref, preference)

    # --- Start the Retry Loop ---
    for attempt in range(max_attempts):
        try:
            # We need to *copy* the pre-calculated groups for this attempt,
            # as the assignment loop will destroy them by removing items.
            
            # .copy() is shallow, but the lists/sets inside are new objects,
            # which is what we want.
            students_by_pref_attempt = {
                pref: list(s_list) for pref, s_list in students_by_pref.items()
            }
            seats_by_pref_attempt = {
                pref: set(s_set) for pref, s_set in seats_by_pref_master.items()
            }

            assignments = []
            num_students = len(master_students)

            # --- Run the Assignment Loop (your existing logic) ---
            last_error = None
            for _ in range(num_students):
                active_preferences = [
                    p for p, s_list in students_by_pref_attempt.items() if s_list
                ]

                if not active_preferences:
                    break  # All students assigned

                # a. Find the most restrictive preference (smallest margin)
                min_preference: Preference = min(
                    active_preferences,
                    key=lambda k: len(seats_by_pref_attempt[k]) - len(students_by_pref_attempt[k])
                )

                min_students: list[Student] = students_by_pref_attempt[min_preference]
                min_seats: set[Seat] = seats_by_pref_attempt[min_preference]

                if not min_seats:
                    # This path failed. Raise the error to trigger a retry.
                    # We re-calculate the original students for the error message
                    original_students_for_pref = arr_to_dict(
                        exam.unassigned_students, get_preference_from_student
                    )[min_preference]
                    raise NotEnoughSeatError(exam, original_students_for_pref, min_preference) 

                # b. Pick a random student and seat
                student = random.choice(min_students)
                seat = random.choice(list(min_seats)) # Convert set to list for choice

                assignments.append((student, seat))

                # c. Remove the student
                min_students.remove(student)

                # d. Remove the seat from *all* preference sets for this attempt
                for pref_set in seats_by_pref_attempt.values():
                    pref_set.discard(seat)

            # --- Success! ---
            # If we get here, the for loop completed without error.
            final_assignments = [
                SeatAssignment(student=s, seat=se) for s, se in assignments
            ]
            return final_assignments

        except NotEnoughSeatError as e:
            # This attempt failed. Loop will continue to the next attempt.
            # print(f"Attempt {attempt + 1} failed. Retrying...")
            last_error = e
            continue
    
    # --- Final Failure ---
    # If we exit the loop, all attempts have failed.
    # Re-raise the last specific error we saw, as it's the most
    # useful debugging information.
    if last_error:
        print("All attempts failed.")
        raise last_error
    
    # Fallback for the (unlikely) case that no error was ever caught
    raise SeatAssignmentError(
        f"Assignment failed after {max_attempts} attempts, but no specific NotEnoughSeatError was caught."
    )


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
