import os
from server import app
from server.models import db
from server.services.email.smtp import SMTPConfig, construct_email, send_emails
import server.services.email.templates as templates
from flask import url_for
from urllib.parse import urljoin

_email_config = SMTPConfig(
    app.config.get('EMAIL_SERVER'),
    app.config.get('EMAIL_PORT'),
    app.config.get('EMAIL_USERNAME'),
    app.config.get('EMAIL_PASSWORD'),
    os.environ.get('EMAIL_SENDER')
)


# how many emails go out over one SMTP connection before the students are marked as emailed
SEND_BATCH_SIZE = 50


def assignment_values(exam, student):
    """The values of the email variables (templates.VARIABLES) for a seated student."""
    seat = student.assignment.seat
    return {
        "NAME": student.first_name,
        "COURSE": exam.offering.name,
        "EXAM": exam.display_name,
        "ROOM": seat.room.display_name,
        "SEAT": seat.display_name,
        "START_TIME": seat.room.start_at_time_display(),
        "DURATION": seat.room.duration_display,
        "URL": urljoin(app.config.get('SERVER_BASE_URL'), url_for('student_single_seat', seat_id=seat.id)),
    }


def substitute_about_assignment(exam, form, student):
    """
    The email `student` gets: its subject, plain-text body and HTML body, all filled in from the
    plain text staff wrote. (None, None, None) for a student without a seat.
    """
    if not student or not student.assignment:
        return None, None, None
    values = assignment_values(exam, student)
    subject = templates.make_substitutions(form.subject.data, values)
    return (subject, templates.render_text(form.body.data, values),
            templates.render_html(subject, form.body.data, values))


def email_about_assignment(exam, form, to_addrs):
    if isinstance(to_addrs, str):
        to_addrs = to_addrs.strip().split(',')
    if not to_addrs:
        return set(), set()
    success_addrs, failure_addrs = set(), set()
    # substitution reads assignment -> seat -> room for every student: load them in one query
    email_student_map = {s.email: s for s in exam.get_students(with_seat=True)}
    email_messages = []
    for to_addr in to_addrs:
        student = email_student_map.get(to_addr, None)
        subject, body, body_html = substitute_about_assignment(exam, form, student)
        if not subject:
            failure_addrs.add(to_addr)
            continue
        email_message = construct_email(
            from_addr=form.from_addr.data,
            to_addr=to_addr,
            subject=subject,
            body=body,
            body_html=body_html,
            cc_addr=form.cc_addr.data,
            bcc_addr=form.bcc_addr.data
        )
        email_messages.append(email_message)
    # save who was emailed after each batch, not once at the end: a send that stops partway (a server
    # timeout, an SMTP error) then still records the students who did get their email
    for start in range(0, len(email_messages), SEND_BATCH_SIZE):
        successful_emails, failed_emails = send_emails(
            smtp=_email_config, messages=email_messages[start:start + SEND_BATCH_SIZE])
        for msg, _ in failed_emails:
            failure_addrs.add(msg['To'])
        for msg, _ in successful_emails:
            success_addrs.add(msg['To'])
            student = email_student_map.get(msg['To'], None)
            if student:
                student.assignment.emailed = True
        db.session.commit()
    return success_addrs, failure_addrs


def send_test_email(exam, form, student, to_addr):
    """
    Sends the email `student` would get to `to_addr` instead, with "[TEST]" before the subject, so
    staff can check it before emailing everyone. Nobody is CC'd or BCC'd, and the student is
    neither emailed nor marked as emailed. Returns whether it was sent.
    """
    subject, body, body_html = substitute_about_assignment(exam, form, student)
    if not subject:
        return False
    message = construct_email(
        from_addr=form.from_addr.data,
        to_addr=to_addr,
        subject=f'[TEST] {subject}',
        body=body,
        body_html=body_html,
    )
    successful_emails, _ = send_emails(smtp=_email_config, messages=[message])
    return bool(successful_emails)
