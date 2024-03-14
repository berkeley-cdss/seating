from server import app
from server.models import db
from server.services.email.smtp import SMTPConfig, construct_email, send_emails
import server.services.email.templates as templates
from server.typings.enum import EmailTemplate
from flask import url_for
from urllib.parse import urljoin

_email_config = SMTPConfig(
    app.config.get('EMAIL_SERVER'),
    app.config.get('EMAIL_PORT'),
    app.config.get('EMAIL_USERNAME'),
    app.config.get('EMAIL_PASSWORD')
)


def substitute_about_assignment(exam, form, student):
    if not student or not student.assignment:
        return None, None
    assignment = student.assignment
    subject = templates.make_substitutions(form.subject.data, {"EXAM": exam.display_name})
    body = templates.make_substitutions(form.body.data,
                                        {"NAME": assignment.student.first_name,
                                         "COURSE": exam.offering.name,
                                         "EXAM": exam.display_name,
                                         "ROOM": assignment.seat.room.display_name,
                                         "SEAT": assignment.seat.display_name,
                                         "START_TIME": assignment.seat.room.start_at_time_display(),
                                         "DURATION": assignment.seat.room.duration_display,
                                         "URL": urljoin(
                                             app.config.get('SERVER_BASE_URL'),
                                             url_for('student_single_seat',
                                                     seat_id=assignment.seat.id)),
                                         })
    return subject, body


def email_about_assignment(exam, form, to_addrs):
    if isinstance(to_addrs, str):
        to_addrs = to_addrs.strip().split(',')
    if not to_addrs:
        return set(), set()
    success_addrs, failure_addrs = set(), set()
    email_student_map = {s.email: s for s in exam.students}
    email_messages = []
    for to_addr in to_addrs:
        student = email_student_map.get(to_addr, None)
        subject, body = substitute_about_assignment(exam, form, student)
        if not subject or not body:
            failure_addrs.add(to_addr)
            continue
        email_message = construct_email(
            from_addr=form.from_addr.data,
            to_addr=to_addr,
            subject=subject,
            body=body,
            body_html=body if form.body_html else None,
            cc_addr=form.cc_addr.data,
            bcc_addr=form.bcc_addr.data
        )
        email_messages.append(email_message)
    successful_emails, failed_emails = send_emails(smtp=_email_config, messages=email_messages)
    for msg, _ in failed_emails:
        failure_addrs.add(msg['To'])
    for msg, _ in successful_emails:
        success_addrs.add(msg['To'])
        student = email_student_map.get(msg['To'], None)
        if student:
            student.assignment.emailed = True
    db.session.commit()
    return success_addrs, failure_addrs
