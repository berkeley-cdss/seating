import random

from server.models import Room, Seat, SeatAssignment, Student


def collect(s, key=lambda x: x):
    d = {}
    for x in s:
        k = key(x)
        if k in d:
            d[k].append(x)
        else:
            d[k] = [x]
    return d


def assign_students(exam):
    """The strategy: look for students whose requirements are the most
    restrictive (i.e. have the fewest possible seats). Randomly assign them
    a seat. Repeat.
    """
    students = set(Student.query.filter_by(
        exam_id=exam.id, assignment=None
    ).all())
    seats = set(Seat.query.join(Seat.room).filter(
        Room.exam_id == exam.id,
        Seat.assignment is None,
    ).all())

    def seats_available(preference):
        wants, avoids = preference
        return [
            seat for seat in seats
            if all(a in seat.attributes for a in wants) and
            all(a not in seat.attributes for a in avoids)
        ]

    assignments = []
    while students:
        students_by_preference = collect(students, key=lambda student: (
            frozenset(student.wants), frozenset(student.avoids)))
        seats_by_preference = {
            preference: seats_available(preference)
            for preference in students_by_preference
        }
        min_preference = min(seats_by_preference,
                             key=lambda k: len(seats_by_preference[k]))
        min_students = students_by_preference[min_preference]
        min_seats = seats_by_preference[min_preference]
        if not min_seats:
            return 'Assignment failed! No more seats for preference {}'.format(min_preference)

        student = random.choice(min_students)
        seat = random.choice(min_seats)

        students.remove(student)
        seats.remove(seat)

        assignments.append(SeatAssignment(student=student, seat=seat))
    return assignments
