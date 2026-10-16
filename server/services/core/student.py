import re

from markupsafe import Markup

from server.services.core.assign import get_preference_from_student, is_seat_valid_for_preference
from server.typings.enum import AssignmentImportStrategy, \
    MissingRowImportStrategy, NewRowImportStrategy, UpdatedRowImportStrategy
from server.typings.exception import DataValidationError
from server.models import db, Room, Seat, SeatAssignment, Student


SPECIAL_HEADERS = ['email', 'name', 'bcourses id', 'canvas id', 'student id', 'emailed', 'seat id', 'assignment',
                   'session name', 'room name', 'seat name', 'public seat url']


class StudentImportConfig:
    def __init__(self, *, revalidate_existing_assignments=True,
                 assignment_import_strategy: AssignmentImportStrategy = AssignmentImportStrategy.REVALIDATE,
                 updated_student_info_import_strategy: UpdatedRowImportStrategy = UpdatedRowImportStrategy.MERGE,
                 updated_preference_import_strategy: UpdatedRowImportStrategy = UpdatedRowImportStrategy.OVERWRITE,
                 new_student_import_strategy: NewRowImportStrategy = NewRowImportStrategy.APPEND,
                 missing_student_import_strategy: MissingRowImportStrategy = MissingRowImportStrategy.IGNORE
                 ):
        self.revalidate_existing_assignments = revalidate_existing_assignments
        self.assignment_import_strategy = assignment_import_strategy
        self.updated_preference_import_strategy = updated_preference_import_strategy
        self.updated_student_info_import_strategy = updated_student_info_import_strategy
        self.new_student_import_strategy = new_student_import_strategy
        self.missing_student_import_strategy = missing_student_import_strategy


def room_to_attr(room: Room):
    return room_id_to_attr(room.id)


def attr_to_room(attr: str) -> Room | None:
    room_id = attr_to_room_id(attr)
    return db.session.get(Room, int(room_id)) if room_id else None


def room_id_to_attr(room_id: int):
    return f'room:{str(room_id)}'


def attr_to_room_id(attr: str) -> None | str:
    if not is_room_attr(attr):
        return None
    return attr[5:]


def normalize_id(value) -> str | None:
    """
    Clean up a canvas id or student id read from a spreadsheet, so it matches the stored one:
    drop surrounding whitespace, and the '.0' a spreadsheet adds when it keeps the id as a
    number (234567.0). Returns None when there is no id.
    """
    if value is None:
        return None
    value = re.sub(r'^(\d+)\.0+$', r'\1', str(value).strip())
    return value or None


class InvalidRow:
    """
    A spreadsheet row the import skipped: which row it is (counting the header as row 1),
    who it is about, as far as the row says, and why it was skipped.
    """

    def __init__(self, number, reason, *, name=None, email=None, canvas_id=None, sid=None):
        self.number = number
        self.reason = reason
        self.who = ', '.join(part for part in [
            name, email,
            f'canvas id {canvas_id}' if canvas_id else None,
            f'student id {sid}' if sid else None,
        ] if part) or 'no name, email or ids'

    def __str__(self):
        return f'Row {self.number} ({self.who}): {self.reason}'


def describe_invalid_rows(invalid_rows, limit=10):
    """
    A message listing the skipped rows and why, for staff to fix the spreadsheet. The rows come
    from an uploaded file, so each is escaped, and the message is Markup so that templates
    which autoescape do not escape it a second time.
    """
    count = len(invalid_rows)
    lines = [Markup(f"Skipped {count} {'row' if count == 1 else 'rows'}:")]
    lines += [Markup('- {}').format(str(row)) for row in invalid_rows[:limit]]
    if count > limit:
        lines.append(Markup(f'- and {count - limit} more'))
    return Markup('\n').join(lines)


class StudentMatcher:
    """
    Finds the student a spreadsheet row is about: by canvas id, falling back to student id,
    then email (ignoring case). It knows the exam's students and the ones of rows seen so far,
    so a student listed on several rows is not created twice.
    """

    def __init__(self, students):
        self.by_canvas_id, self.by_sid, self.by_email = {}, {}, {}
        self.listed = set()
        for student in students:
            self.add(student)

    def add(self, student):
        self.by_canvas_id[str(student.canvas_id)] = student
        if normalize_id(student.sid):
            self.by_sid.setdefault(normalize_id(student.sid), student)
        if student.email:
            self.by_email.setdefault(student.email.strip().lower(), student)

    def find(self, canvas_id, sid, email):
        """
        Returns the matching student or None, and if the row cannot be imported, why: it is someone
        we know by student id or email, but with another canvas id, or it has no canvas id and
        matches no one.
        """
        student = self.by_canvas_id.get(canvas_id) if canvas_id else None
        if student:
            return student, None
        by_sid = self.by_sid.get(sid) if sid else None
        by_email = self.by_email.get(email.lower()) if email else None
        student, matched_on = (by_sid, 'student id') if by_sid else (by_email, 'email')
        if student and canvas_id:
            # we cannot tell which canvas id is right, and creating another student would duplicate them
            return None, (f'its {matched_on} belongs to {student.name} (canvas id {student.canvas_id}), '
                          f'who has a different canvas id')
        if not student and not canvas_id:
            if sid or email:
                return None, 'no canvas id, and no student has its student id or email'
            return None, 'no canvas id, student id or email'
        return student, None

    def first_listing(self, student):
        """Whether this is the first row for `student`, so it goes into the result lists once."""
        if id(student) in self.listed:
            return False
        self.listed.add(id(student))
        return True


def canvas_id_problem(canvas_id: str) -> str | None:
    """
    Why `canvas_id`, cleaned up by normalize_id, cannot be a Canvas id, or None if it can. Canvas ids
    are whole numbers, and the app's student urls only match digits, so a student stored with
    anything else could never be opened, edited or deleted, nor find their seat on logging in.
    """
    if re.fullmatch(r'[0-9]+', canvas_id):
        return None
    if re.fullmatch(r'[0-9]+(\.[0-9]+)?[eE][+-]?[0-9]+', canvas_id):
        return (f'canvas id {canvas_id} is in scientific notation, which a spreadsheet uses for long numbers '
                f'and which loses their last digits: format the column as text and export again')
    return f'canvas id {canvas_id} is not a number'


def is_normal_attr(attr: str):
    return not is_room_attr(attr) and attr not in SPECIAL_HEADERS


def is_room_attr(attr: str):
    return attr.startswith('room:') and attr not in SPECIAL_HEADERS


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
    students_ids_to_remove = []
    new_assignment_ids = set()
    exam_room_ids = {str(room.id) for room in exam.rooms}

    # Load everything the per-row logic looks up once, up front, instead of
    # 1 student query + 1 assignment query + 1-2 seat queries for every row.
    existing_students_by_canvas_id = {
        str(student.canvas_id): student for student in exam.get_students(with_seat=True)}
    matcher = StudentMatcher(existing_students_by_canvas_id.values())
    exam_seats = exam.get_seats() if config.assignment_import_strategy != AssignmentImportStrategy.IGNORE else []
    seats_by_id = {seat.id: seat for seat in exam_seats}
    seats_by_room_and_name = {}
    for seat in exam_seats:
        seats_by_room_and_name.setdefault((seat.room_id, seat.name), []).append(seat)
    rooms_by_display_name = {}
    for room in exam.rooms:
        rooms_by_display_name.setdefault(room.name_and_start_at_time_display(), room)

    for row_number, row in enumerate(rows, start=2):
        canvas_id = normalize_id(row.pop('bcourses id', row.pop('canvas id', None)))
        sid = normalize_id(row.pop('student id', None))
        email = (row.pop('email', None) or '').strip() or None
        name = row.pop('name', None)

        def invalid(reason):
            invalid_students.append(InvalidRow(row_number, reason, name=name, email=email, canvas_id=canvas_id, sid=sid))

        problem = canvas_id and canvas_id_problem(canvas_id)
        if not problem:
            student, problem = matcher.find(canvas_id, sid, email)
        if problem:
            invalid(problem)
            continue
        is_new = not student
        if is_new:
            student = Student(exam_id=exam.id, canvas_id=canvas_id)
            if config.new_student_import_strategy == NewRowImportStrategy.IGNORE:
                invalid('new student, and the import is set to ignore new students')
                continue

        # update name, email and sid, emailed
        if not config.updated_student_info_import_strategy == UpdatedRowImportStrategy.IGNORE:
            overwrite = not is_new and config.updated_student_info_import_strategy == UpdatedRowImportStrategy.OVERWRITE
            student.name = name if overwrite else (name or student.name)
            student.email = email if overwrite else (email or student.email)
            missing = [field for field, value in [('name', student.name), ('email', student.email)] if not value]
            if missing:
                invalid(f"no {' or '.join(missing)}")
                continue
            student.sid = sid if overwrite else (sid or student.sid)
            emailed = row.pop('emailed', 'false')

        # parse out preferences: wants and avoids should be mutually exclusive
        if not config.updated_preference_import_strategy == UpdatedRowImportStrategy.IGNORE:
            overwrite_pref = not is_new and config.updated_preference_import_strategy == UpdatedRowImportStrategy.OVERWRITE
            wants = {k.lower() for k, v in row.items() if is_normal_attr(k) and v.lower() == 'true'}
            student.wants = wants if (is_new or overwrite_pref) else student.wants.union(wants)
            avoids = {k.lower() for k, v in row.items() if is_normal_attr(k) and v.lower() == 'false'}
            student.avoids = avoids if (is_new or overwrite_pref) else student.avoids.union(avoids)
            # room preferences may only reference rooms of this exam: a CSV exported from another exam
            # carries that exam's room ids, and merging keeps ids of rooms deleted since, so filter
            # after merging to drop both
            room_wants = {attr_to_room_id(k) for k, v in row.items() if is_room_attr(k) and v.lower() == 'true'}
            room_wants = room_wants if (is_new or overwrite_pref) else student.room_wants.union(room_wants)
            student.room_wants = room_wants & exam_room_ids
            room_avoids = {attr_to_room_id(k) for k, v in row.items() if is_room_attr(k) and v.lower() == 'false'}
            room_avoids = room_avoids if (is_new or overwrite_pref) else student.room_avoids.union(room_avoids)
            student.room_avoids = room_avoids & exam_room_ids
            both = sorted(student.wants & student.avoids) + [
                room.name_and_start_at_time_display() for room in exam.get_rooms(student.room_wants & student.room_avoids)]
            if both:
                invalid(f"both wants and avoids {', '.join(both)}")
                continue

        # revalidate existing assignments
        if config.revalidate_existing_assignments:
            new_preference = get_preference_from_student(student)
            if student.assignment and not is_seat_valid_for_preference(student.assignment.seat, new_preference):
                student.assignment = None

        # some rows have already have a prev seat, or have seat assignment specified, try use that if that is valid
        # try to match id first, then match name
        if config.assignment_import_strategy != AssignmentImportStrategy.IGNORE:
            ignore_restrictions_for_new = config.assignment_import_strategy == AssignmentImportStrategy.FORCE
            seat_id = row.pop('seat id', row.pop('assignment', None))
            if seat_id:
                # only this exam's seats are in the map, so a seat from another exam is simply not found
                seat = seats_by_id.get(int(seat_id))
                if seat and not seat.assignment \
                        and (ignore_restrictions_for_new or is_seat_valid_for_preference(seat, new_preference)) \
                        and seat_id not in new_assignment_ids:
                    new_assignment_ids.add(seat_id)
                    student.assignment = SeatAssignment(seat=seat, emailed=emailed == 'true')
            else:
                room_name = row.pop('session name', row.pop('room name', None))
                seat_name = row.pop('seat name', None)
                if room_name and seat_name:
                    room_inferred = rooms_by_display_name.get(room_name)
                    seats_inferred: list[Seat] = []
                    if room_inferred:
                        seats_inferred.extend(seats_by_room_and_name.get((room_inferred.id, seat_name), []))
                        if not seats_inferred and 'Movable Seat' in seat_name:
                            seats_inferred.extend(seats_by_room_and_name.get((room_inferred.id, None), []))
                    for seat in seats_inferred:
                        if not seat.assignment \
                                and (ignore_restrictions_for_new or is_seat_valid_for_preference(seat, new_preference))\
                                and seat.id not in new_assignment_ids:
                            new_assignment_ids.add(seat.id)
                            student.assignment = SeatAssignment(seat=seat, emailed=emailed == 'true')
                            break

        matcher.add(student)
        if not matcher.first_listing(student):
            continue
        if is_new:
            new_students.append(student)
        else:
            updated_students.append(student)

    if config.missing_student_import_strategy == MissingRowImportStrategy.DELETE:
        imported_canvas_ids = {student.canvas_id for student in new_students + updated_students}
        for student in existing_students_by_canvas_id.values():
            if student.canvas_id not in imported_canvas_ids:
                students_ids_to_remove.append(student.id)

    return new_students, updated_students, invalid_students, students_ids_to_remove
