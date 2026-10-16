import unittest
from unittest.mock import MagicMock, patch, call

from server.services.core.assign import (
    Preference,
    is_seat_valid_for_preference,
    filter_seats_by_preference,
    get_preference_from_student,
    assign_students,
    assign_single_student
)

from server.typings.exception import NotEnoughSeatError, SeatOverrideError

# Mock Models
MockStudent = MagicMock
MockSeat = MagicMock
MockRoom = MagicMock
MockExam = MagicMock
# Mock the assignment to just return a tuple of its inputs for easy testing
MockSeatAssignment = MagicMock(side_effect=lambda student, seat: (student, seat))


class TestPreferenceClass(unittest.TestCase):
    """Tests the Preference data class."""

    def test_equality(self):
        p1 = Preference(wants={'a'}, avoids={'b'}, room_wants={'1'}, room_avoids={'2'})
        p2 = Preference(wants={'a'}, avoids={'b'}, room_wants={'1'}, room_avoids={'2'})
        self.assertEqual(p1, p2)

    def test_inequality(self):
        p1 = Preference(wants={'a'}, avoids={'b'}, room_wants={'1'}, room_avoids={'2'})
        p3 = Preference(wants={'c'}, avoids={'b'}, room_wants={'1'}, room_avoids={'2'})
        self.assertNotEqual(p1, p3)

    def test_hashability(self):
        p1 = Preference(wants={'a'}, avoids={'b'}, room_wants={'1'}, room_avoids={'2'})
        p2 = Preference(wants={'a'}, avoids={'b'}, room_wants={'1'}, room_avoids={'2'})
        p3 = Preference(wants={'c'}, avoids={'b'}, room_wants={'1'}, room_avoids={'2'})

        pref_set = {p1, p2, p3}
        # p1 and p2 are duplicates, so the set should only have 2 unique items
        self.assertEqual(len(pref_set), 2)
        self.assertIn(p1, pref_set)
        self.assertIn(p3, pref_set)


class TestSeatPreferenceLogic(unittest.TestCase):
    """Tests the core validation and filtering functions."""

    def setUp(self):
        """Set up common mock rooms and seats for testing."""
        self.room1 = MockRoom(id=1)
        self.room2 = MockRoom(id=2)

        self.seat_a_window = MockSeat(attributes={'A', 'Window'}, room=self.room1)
        self.seat_b_aisle = MockSeat(attributes={'B', 'Aisle'}, room=self.room1)
        self.seat_c_window = MockSeat(attributes={'C', 'Window'}, room=self.room2)

    def test_is_seat_valid_all_pass(self):
        # Pref: wants 'window' (lowercase), avoids 'aisle', wants room 1
        pref = Preference(wants={'window'}, avoids={'aisle'}, room_wants={'1'}, room_avoids={'2'})
        # Seat: has 'Window' (uppercase), in room 1
        is_valid = is_seat_valid_for_preference(self.seat_a_window, pref)
        self.assertTrue(is_valid)

    def test_is_seat_valid_wants_fail(self):
        # Pref: wants 'D'
        pref = Preference(wants={'D'}, avoids=set(), room_wants=set(), room_avoids=set())
        is_valid = is_seat_valid_for_preference(self.seat_a_window, pref)
        self.assertFalse(is_valid)

    def test_is_seat_valid_avoids_fail(self):
        # Pref: avoids 'aisle' (lowercase)
        pref = Preference(wants=set(), avoids={'aisle'}, room_wants=set(), room_avoids=set())
        # Seat: has 'Aisle' (uppercase)
        is_valid = is_seat_valid_for_preference(self.seat_b_aisle, pref)
        self.assertFalse(is_valid)

    def test_is_seat_valid_room_wants_fail(self):
        # Pref: wants room 1
        pref = Preference(wants=set(), avoids=set(), room_wants={'1'}, room_avoids=set())
        # Seat: in room 2
        is_valid = is_seat_valid_for_preference(self.seat_c_window, pref)
        self.assertFalse(is_valid)

    def test_is_seat_valid_room_avoids_fail(self):
        # Pref: avoids room 2
        pref = Preference(wants=set(), avoids=set(), room_wants=set(), room_avoids={'2'})
        # Seat: in room 2
        is_valid = is_seat_valid_for_preference(self.seat_c_window, pref)
        self.assertFalse(is_valid)

    def test_is_seat_valid_empty_pref(self):
        # An empty preference should be valid for any seat
        pref = Preference(wants=set(), avoids=set(), room_wants=set(), room_avoids=set())
        is_valid = is_seat_valid_for_preference(self.seat_a_window, pref)
        self.assertTrue(is_valid)

    def test_filter_seats_by_preference(self):
        seats = [self.seat_a_window, self.seat_b_aisle, self.seat_c_window]
        # Pref: wants 'window'
        pref = Preference(wants={'window'}, avoids=set(), room_wants=set(), room_avoids=set())

        filtered = filter_seats_by_preference(seats, pref)

        self.assertEqual(len(filtered), 2)
        self.assertIn(self.seat_a_window, filtered)
        self.assertIn(self.seat_c_window, filtered)
        self.assertNotIn(self.seat_b_aisle, filtered)

    def test_get_preference_from_student(self):
        student = MockStudent(
            wants={'a'}, avoids={'b'}, room_wants={'1'}, room_avoids={'2'}
        )
        pref = get_preference_from_student(student)

        expected_pref = Preference(wants={'a'}, avoids={'b'}, room_wants={'1'}, room_avoids={'2'})
        self.assertEqual(pref, expected_pref)


@patch('server.services.core.assign.SeatAssignment', MockSeatAssignment)
@patch('server.services.core.assign.arr_to_dict')
@patch('server.services.core.assign.random.choice')
class TestAssignStudents(unittest.TestCase):
    """Tests the main 'assign_students' function."""

    def setUp(self):
        self.room1 = MockRoom(id=1, name='R1')
        self.room1.__repr__ = lambda s: f"<MockRoom id={s.id}>"
        self.room2 = MockRoom(id=2, name='R2')
        self.room2.__repr__ = lambda s: f"<MockRoom id={s.id}>"

        # Preferences
        self.pref_a = Preference(wants={'A'}, avoids=set(), room_wants=set(), room_avoids=set())
        self.pref_b = Preference(wants={'B'}, avoids=set(), room_wants=set(), room_avoids=set())
        self.pref_c_room1 = Preference(wants={'C'}, avoids=set(), room_wants={'1'}, room_avoids=set())

        # Students
        self.s_a1 = MockStudent(name='s_a1', wants={'A'}, avoids=set(), room_wants=set(), room_avoids=set())
        self.s_a1.__repr__ = lambda s: f"<MockStudent name={s.name}>"
        self.s_b1 = MockStudent(name='s_b1', wants={'B'}, avoids=set(), room_wants=set(), room_avoids=set())
        self.s_b1.__repr__ = lambda s: f"<MockStudent name={s.name}>"
        self.s_b2 = MockStudent(name='s_b2', wants={'B'}, avoids=set(), room_wants=set(), room_avoids=set())
        self.s_b2.__repr__ = lambda s: f"<MockStudent name={s.name}>"

        # Seats
        self.seat_a1 = MockSeat(name='seat_a1', attributes={'A'}, room=self.room1)
        self.seat_a1.__repr__ = lambda s: f"<MockSeat name={s.name}>"
        self.seat_a2 = MockSeat(name='seat_a2', attributes={'A'}, room=self.room2)
        self.seat_a2.__repr__ = lambda s: f"<MockSeat name={s.name}>"
        self.seat_b1 = MockSeat(name='seat_b1', attributes={'B'}, room=self.room1)
        self.seat_b1.__repr__ = lambda s: f"<MockSeat name={s.name}>"
        self.seat_ab = MockSeat(name='seat_ab', attributes={'A', 'B'}, room=self.room2)
        self.seat_ab.__repr__ = lambda s: f"<MockSeat name={s.name}>"

        self.exam = MockExam()
        self.exam.__repr__ = lambda s: "<MockExam>"

    def test_assign_no_students(self, mock_random_choice, mock_arr_to_dict):
        self.exam.unassigned_students = set()
        self.exam.unassigned_seats = {self.seat_a1}

        assignments = assign_students(self.exam)

        self.assertEqual(assignments, [])
        mock_arr_to_dict.assert_not_called()

    def test_assign_simple_one_to_one(self, mock_random_choice, mock_arr_to_dict):
        # 1 student, 1 seat, 1 preference
        self.exam.unassigned_students = {self.s_a1}
        self.exam.unassigned_seats = {self.seat_a1}

        # Mock the grouping functions
        mock_arr_to_dict.return_value = {self.pref_a: [self.s_a1]}
        # Mock random.choice to be deterministic
        mock_random_choice.side_effect = [self.s_a1, self.seat_a1]

        assignments = assign_students(self.exam)

        self.assertEqual(len(assignments), 1)
        # MockSeatAssignment returns (student, seat)
        self.assertEqual(assignments[0], (self.s_a1, self.seat_a1))
        mock_arr_to_dict.assert_called_once_with(
            {self.s_a1}, key_getter=get_preference_from_student
        )
        # Check what random.choice was *called with*
        expected_calls = [
            call([self.s_a1]),      # 1. Called with list of students
            call([self.seat_a1])    # 2. Called with list(set_of_seats)
        ]
        mock_random_choice.assert_has_calls(expected_calls)

    def test_assign_restrictive_logic(self, mock_random_choice, mock_arr_to_dict):
        """
        Tests the core logic: "assign most restrictive preference first".

        Scenario:
        - Pref A: 1 student (s_a1), 2 seats match (seat_a1, seat_ab)
        - Pref B: 1 student (s_b1), 1 seat matches (seat_ab)

        Expected:
        1. `seats_by_pref[pref_a]` has length 2.
        2. `seats_by_pref[pref_b]` has length 1.
        3. `min_preference` will be `pref_b`.
        4. s_b1 is assigned first, getting seat_ab.
        5. `seat_ab` is removed from all lists.
        6. `min_preference` is now `pref_a`.
        7. s_a1 is assigned second, getting seat_a1.
        """
        self.exam.unassigned_students = {self.s_a1, self.s_b1}
        self.exam.unassigned_seats = {self.seat_a1, self.seat_ab}

        mock_arr_to_dict.return_value = {
            self.pref_a: [self.s_a1],
            self.pref_b: [self.s_b1]
        }

        # Mock random.choice selections
        # Loop 1 (Pref B): picks s_b1, then seat_ab
        # Loop 2 (Pref A): picks s_a1, then seat_a1
        mock_random_choice.side_effect = [
            self.s_b1,  # 1. choice from min_students [s_b1]
            self.seat_ab,   # 2. choice from min_seats {seat_ab}
            self.s_a1,  # 3. choice from min_students [s_a1]
            self.seat_a1  # 4. choice from min_seats {seat_a1} (seat_ab was removed)
        ]

        assignments = assign_students(self.exam)

        self.assertEqual(len(assignments), 2)
        # Check that assignments happened in the expected order
        self.assertEqual(assignments[0], (self.s_b1, self.seat_ab))
        self.assertEqual(assignments[1], (self.s_a1, self.seat_a1))

    def test_assign_not_enough_seats_error(self, mock_random_choice, mock_arr_to_dict):
        """
        Tests that NotEnoughSeatError is raised if a preference group
        runs out of seats.

        Scenario:
        - Pref B: 2 students (s_b1, s_b2), 1 seat (seat_b1)

        Expected:
        1. `min_preference` is `pref_b` (1 seat).
        2. s_b1 is assigned seat_b1.
        3. Loop 2: `min_preference` is `pref_b` (0 seats).
        4. `if not min_seats:` block is triggered.
        5. `NotEnoughSeatError` is raised.
        """
        self.exam.unassigned_students = {self.s_b1, self.s_b2}
        self.exam.unassigned_seats = {self.seat_b1}

        # Mock the initial grouping
        mock_arr_to_dict.side_effect = [
            # First call inside assign_students
            {self.pref_b: [self.s_b1, self.s_b2]},
            # Second call inside the error-raising block
            {self.pref_b: [self.s_b1, self.s_b2]}
        ]

        # Loop 1: picks s_b1, then seat_b1
        mock_random_choice.side_effect = [self.s_b1, self.seat_b1]

        with self.assertRaises(NotEnoughSeatError) as cm:
            assign_students(self.exam)

        # Check that the error was raised with the correct info
        self.assertEqual(cm.exception.preference, self.pref_b)
        self.assertIn(self.s_b1, cm.exception.students)
        self.assertIn(self.s_b2, cm.exception.students)


@patch('server.services.core.assign.SeatAssignment', MockSeatAssignment)
@patch('server.services.core.assign.random.choice')
class TestAssignSingleStudent(unittest.TestCase):
    """Tests the 'assign_single_student' utility function."""

    def setUp(self):
        self.room1 = MockRoom(id=1, name='R1')
        self.room1.__repr__ = lambda s: f"<MockRoom id={s.id}>"
        self.room2 = MockRoom(id=2, name='R2')
        self.room2.__repr__ = lambda s: f"<MockRoom id={s.id}>"

        # Pref C: wants 'C', wants room 1
        self.pref_c_room1 = Preference(wants={'C'}, avoids=set(), room_wants={'1'}, room_avoids=set())
        self.student_c = MockStudent(
            name='s_c1', wants={'C'}, avoids=set(), room_wants={'1'}, room_avoids=set()
        )
        # make mock printable
        self.student_c.__repr__ = lambda s: f"<MockStudent name={s.name}>"

        # A valid seat for student_c
        self.seat_c1 = MockSeat(name='seat_c1', attributes={'C'}, room=self.room1)
        self.seat_c1.__repr__ = lambda s: f"<MockSeat name={s.name}>"
        # An invalid seat (wrong room)
        self.seat_c2_wrong_room = MockSeat(name='seat_c2', attributes={'C'}, room=self.room2)
        self.seat_c2_wrong_room.__repr__ = lambda s: f"<MockSeat name={s.name}>"
        # An invalid seat (wrong attr)
        self.seat_d1 = MockSeat(name='seat_d1', attributes={'D'}, room=self.room1)
        self.seat_d1.__repr__ = lambda s: f"<MockSeat name={s.name}>"

        self.exam = MockExam()
        self.exam.__repr__ = lambda s: "<MockExam>"
        # Note: exam.unassigned_seats is a list in this function's logic
        self.exam.unassigned_seats = [self.seat_c1, self.seat_c2_wrong_room, self.seat_d1]

    def test_assign_single_auto_success(self, mock_random_choice):
        # Auto-assign, no seat specified, respects restrictions

        # `filter_seats_by_preference` will return [self.seat_c1]
        # mock random.choice to pick it
        mock_random_choice.return_value = self.seat_c1

        assignment = assign_single_student(self.exam, self.student_c, ignore_restrictions=False)

        self.assertEqual(assignment, (self.student_c, self.seat_c1))
        mock_random_choice.assert_called_once_with([self.seat_c1])

    def test_assign_single_auto_no_valid_seats_error(self, mock_random_choice):
        # Auto-assign, but no seats meet preference
        self.exam.unassigned_seats = [self.seat_c2_wrong_room, self.seat_d1]

        with self.assertRaises(NotEnoughSeatError):
            assign_single_student(self.exam, self.student_c, ignore_restrictions=False)

        mock_random_choice.assert_not_called()

    def test_assign_single_auto_ignore_restrictions(self, mock_random_choice):
        # Auto-assign, ignoring restrictions. Should pick from *all* unassigned seats.
        self.exam.unassigned_seats = [self.seat_c1, self.seat_c2_wrong_room, self.seat_d1]
        mock_random_choice.return_value = self.seat_d1   # Pick an otherwise invalid seat

        assignment = assign_single_student(self.exam, self.student_c, ignore_restrictions=True)

        self.assertEqual(assignment, (self.student_c, self.seat_d1))
        # Verifies it's choosing from all 3 seats
        mock_random_choice.assert_called_once_with(
            [self.seat_c1, self.seat_c2_wrong_room, self.seat_d1]
        )

    def test_assign_single_specific_seat_success(self, mock_random_choice):
        # Assign to a specific, valid seat
        assignment = assign_single_student(
            self.exam, self.student_c, seat=self.seat_c1, ignore_restrictions=False
        )

        self.assertEqual(assignment, (self.student_c, self.seat_c1))
        mock_random_choice.assert_not_called()   # No random choice needed

    def test_assign_single_specific_seat_override_error(self, mock_random_choice):
        # Assign to a specific seat that is NOT valid (wrong room)
        with self.assertRaises(SeatOverrideError):
            assign_single_student(
                self.exam, self.student_c, seat=self.seat_c2_wrong_room, ignore_restrictions=False
            )

    def test_assign_single_specific_seat_not_in_exam_error(self, mock_random_choice):
        # Assign to a specific seat that is not in the unassigned list
        seat_taken = MockSeat(name='seat_taken', attributes={'C'}, room=self.room1)
        # Note: seat_taken is not in self.exam.unassigned_seats

        with self.assertRaises(SeatOverrideError):
            assign_single_student(
                self.exam, self.student_c, seat=seat_taken, ignore_restrictions=False
            )

    def test_assign_single_specific_seat_ignore_restrictions_success(self, mock_random_choice):
        # Assign to a specific, "invalid" seat, but ignoring restrictions
        assignment = assign_single_student(
            self.exam, self.student_c, seat=self.seat_d1, ignore_restrictions=True
        )

        self.assertEqual(assignment, (self.student_c, self.seat_d1))
        mock_random_choice.assert_not_called()


if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
