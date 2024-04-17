from server.services.core.assign import get_preference_from_student
from server.services.core.student import room_id_to_attr
from server.services.csv import to_csv_str
from flask import url_for


def export_exam_student_info(exam) -> str:
    """
    Export exam student info to a CSV file.
    """
    headers = set(['name', 'email', 'student id', 'canvas id', 'session name',
                  'seat name', 'emailed', 'room id', 'seat id', 'public seat url'])
    rows = []
    for student in exam.students:
        row_dict = {
            'name': student.name,
            'email': student.email,
            'student id': student.sid,
            'canvas id': student.canvas_id,
            'session name': student.assignment.seat.room.name_and_start_at_time_display() if student.assignment else None,
            'seat name': student.assignment.seat.display_name if student.assignment else None,
            'room id': student.assignment.seat.room.id if student.assignment else None,
            'seat id': student.assignment.seat.id if student.assignment else None,
            'emailed': str(student.assignment.emailed).lower() if student.assignment else None,
            'public seat url': url_for('student_single_seat', seat_id=student.assignment.seat.id, _external=True) if student.assignment else None,
        }
        prefs = get_preference_from_student(student)
        for attr in prefs.wants:
            row_dict[attr] = 'true'
            headers.add(attr)
        for attr in prefs.avoids:
            row_dict[attr] = 'false'
            headers.add(attr)
        for room_id_str in prefs.room_wants:
            attr = room_id_to_attr(room_id_str)
            row_dict[attr] = 'true'
            headers.add(attr)
        for room_id_str in prefs.room_avoids:
            attr = room_id_to_attr(room_id_str)
            row_dict[attr] = 'false'
            headers.add(attr)
        rows.append(row_dict)
    csv_str = to_csv_str(list(headers), rows)
    return csv_str
