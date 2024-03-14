from server.services.core.assign import get_preference_from_student, is_seat_valid_for_preference
from server.typings.enum import AssignmentImportStrategy
from server.typings.exception import DataValidationError
from server.models import Room, Seat, SeatAssignment, Student


class StudentImportConfig:
    def __init__(self, revalidate_existing_assignments=True,
                 new_assignment_import_strategy: AssignmentImportStrategy = AssignmentImportStrategy.REVALIDATE):
        self.revalidate_existing_assignments = revalidate_existing_assignments
        self.new_assignment_import_strategy = new_assignment_import_strategy


def room_to_attr(room: Room):
    return room_id_to_attr(room.id)


def attr_to_room(attr: str) -> Room | None:
    room_id = attr_to_room_id(attr)
    return Room.query.get(int(room_id)) if room_id else None


def room_id_to_attr(room_id: int):
    return f'room:{str(room_id)}'


def attr_to_room_id(attr: str) -> None | str:
    if not is_room_attr(attr):
        return None
    return attr[5:]


def is_room_attr(attr: str):
    return attr.startswith('room:')


def prepare_students(exam, headers, rows, *, config: StudentImportConfig = StudentImportConfig()):
    """
    Prepare a list of students from the spreadsheet data, for the given exam.
    """
    if 'email' not in headers:
        raise DataValidationError('Missing "email" column')
    elif 'name' not in headers:
        raise DataValidationError('Missing "name" column')
    elif 'bcourses id' not in headers and 'canvas id' not in headers:
        raise DataValidationError('Missing "canvas id" column')

    new_students = []
    updated_students = []
    invalid_students = []
    new_assignment_ids = set()

    for row in rows:
        # get canvas id
        canvas_id = row.pop(
            'bcourses id', row.pop('canvas id', None))
        email = row.pop('email', None)
        name = row.pop('name', None)
        if not canvas_id:
            invalid_students.append(row)

        # try matching existing student (by canvas id)
        student = Student.query.filter_by(exam_id=int(exam.id), canvas_id=str(canvas_id)).first()
        is_new = not student
        if is_new:
            student = Student(exam_id=exam.id, canvas_id=canvas_id)

        # upsert name, email and sid, emailed
        student.name = name or student.name
        student.email = email or student.email
        if not student.name or not student.email:
            invalid_students.append(row)
            continue
        student.sid = row.pop('student id', None) or student.sid
        emailed = row.pop('emailed', 'false')

        # parse out preferences: wants and avoids should be mutually exclusive
        student.wants = {k.lower() for k, v in row.items() if v.lower() == 'true' and not is_room_attr(k)}
        student.avoids = {k.lower() for k, v in row.items() if v.lower() == 'false' and not is_room_attr(k)}
        student.room_wants = {attr_to_room_id(k) for k, v in row.items() if v.lower() == 'true' and is_room_attr(k)}
        student.room_avoids = {attr_to_room_id(k) for k, v in row.items() if v.lower() == 'false' and is_room_attr(k)}
        if not student.wants.isdisjoint(student.avoids) \
                or not student.room_wants.isdisjoint(student.room_avoids):
            invalid_students.append(row)
            continue

        # some rows have already have a prev seat, or have seat assignment specified, try use that if that is valid
        # try to match id first, then match name
        if config.revalidate_existing_assignments:
            new_preference = get_preference_from_student(student)
            if student.assignment and not is_seat_valid_for_preference(student.assignment.seat, new_preference):
                student.assignment = None
        if config.new_assignment_import_strategy != AssignmentImportStrategy.IGNORE:
            ignore_restrictions_for_new = config.new_assignment_import_strategy == AssignmentImportStrategy.FORCE
            seat_id = row.pop('seat id', row.pop('assignment', None))
            if seat_id:
                seat = Seat.query.get(int(seat_id))
                if seat and not seat.assignment and seat.room.exam_id == exam.id \
                        and (ignore_restrictions_for_new or is_seat_valid_for_preference(seat, new_preference)) \
                        and seat_id not in new_assignment_ids:
                    new_assignment_ids.add(seat_id)
                    student.assignment = SeatAssignment(student=student, seat=seat, emailed=emailed == 'true')
            else:
                room_name = row.pop('session name', row.pop('room name', None))
                seat_name = row.pop('seat name', None)
                if room_name and seat_name:
                    room_inferred = None
                    for room in exam.rooms:
                        if room.name_and_start_at_time_display() == room_name:
                            room_inferred = room
                            break
                    seats_inferred: list[Seat] = []
                    if room_inferred:
                        seats_inferred.extend(Seat.query.filter_by(room_id=room_inferred.id, name=seat_name).all())
                        if not seats_inferred and 'Movable Seat' in seat_name:
                            seats_inferred.extend(Seat.query.filter_by(room_id=room_inferred.id, name=None).all())
                    for seat in seats_inferred:
                        if not seat.assignment \
                                and (ignore_restrictions_for_new or is_seat_valid_for_preference(seat, new_preference))\
                                and seat.id not in new_assignment_ids:
                            new_assignment_ids.add(seat.id)
                            student.assignment = SeatAssignment(student=student, seat=seat, emailed=emailed == 'true')
                            break

        if is_new:
            new_students.append(student)
        else:
            updated_students.append(student)

    return new_students, updated_students, invalid_students
