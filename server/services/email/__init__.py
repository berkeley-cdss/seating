from server import app
from server.models import db, Exam, SeatAssignment, Offering
from server.services.email.smtp import SMTPConfig, send_email
import server.services.email.templates as templates
from server.typings.enum import EmailTemplate
from flask import url_for
import os

_email_config = SMTPConfig(
    app.config.get('EMAIL_SERVER'),
    app.config.get('EMAIL_PORT'),
    app.config.get('EMAIL_USERNAME'),
    app.config.get('EMAIL_PASSWORD')
)


def email_students(exam: Exam, form):
    ASSIGNMENT_PER_PAGE = 500
    page_number = 1

    while True:
        assignments = exam.get_assignments(
            emailed=False,
            limit=ASSIGNMENT_PER_PAGE,
            offset=(page_number - 1) * ASSIGNMENT_PER_PAGE
        )
        if not assignments:
            break
        page_number += 1

        for assignment in assignments:
            if _email_single_assignment(exam.offering, exam, assignment, form):
                assignment.emailed = True

        db.session.commit()


def _email_single_assignment(offering: Offering, exam: Exam, assignment: SeatAssignment, form) -> bool:
    seat_path = url_for('student_single_seat', seat_id=assignment.seat.id)
    seat_absolute_path = os.path.join(app.config['DOMAIN'], seat_path)
    student_email = \
        templates.get_email(EmailTemplate.ASSIGNMENT_INFORM_EMAIL,
                            {"EXAM": exam.display_name},
                            {"NAME": assignment.student.first_name,
                                "COURSE": offering.name,
                                "EXAM": exam.display_name,
                                "ROOM": assignment.seat.room.display_name,
                                "SEAT": assignment.seat.name,
                                "URL": seat_absolute_path,
                                "ADDITIONAL_INFO": form.additional_text.data,
                                "SIGNATURE": form.from_name.data})

    return send_email(smtp=_email_config,
                      from_addr=form.from_email.data,
                      to_addr=assignment.student.email,
                      subject=student_email.subject,
                      body=student_email.body,
                      body_html=student_email.body if student_email.body_html else None)


# def email_students(exam, form):
#     """Emails students in batches of 900"""
#     sg = sendgrid.SendGridAPICslient(api_key=app.config['SENDGRID_API_KEY'])
#     test = form.test_email.data
#     while True:
#         limit = 1 if test else 900
#         assignments = SeatAssignment.query.join(SeatAssignment.seat).join(Seat.room).filter(
#             Room.exam_id == exam.id,
#             not SeatAssignment.emailed
#         ).limit(limit).all()
#         if not assignments:
#             break

#         data = {
#             'personalizations': [
#                 {
#                     'to': [
#                         {
#                             'email': test if test else assignment.student.email,
#                         }
#                     ],
#                     'substitutions': {
#                         '-name-': assignment.student.first_name,
#                         '-room-': assignment.seat.room.display_name,
#                         '-seat-': assignment.seat.name,
#                         '-seatid-': str(assignment.seat.id),
#                     },
#                 }
#                 for assignment in assignments
#             ],
#             'from': {
#                 'email': form.from_email.data,
#                 'name': form.from_name.data,
#             },
#             'subject': form.subject.data,
#             'content': [
#                 {
#                     'type': 'text/plain',
#                     'value': '''
# Hi -name-,

# Here's your assigned seat for {}:

# Room: -room-

# Seat: -seat-

# You can view this seat's position on the seating chart at:
# {}/seat/-seatid-/

# {}
# '''.format(exam.display_name, app.config['DOMAIN'], form.additional_text.data)
#                 },
#             ],
#         }

#         response = sg.client.mail.send.post(request_body=data)
#         if response.status_code < 200 or response.status_code >= 400:
#             raise Exception('Could not send mail. Status: {}. Body: {}'.format(
#                 response.status_code, response.body
#             ))
#         if test:
#             return
#         for assignment in assignments:
#             assignment.emailed = True
#         db.session.commit()
