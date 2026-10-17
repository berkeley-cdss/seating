"""
Assignment emails are filled in by replacing {{KEY}} placeholders with names and other values that
come from imports and staff input. In an HTML body the values must be escaped; in plain text, and
in the subject, they must not be. Values are taken literally, backslashes included.
"""
import pytest

from server import app as flask_app
from server.forms import EmailForm
from server.models import db, Exam, Student
import server.services.email as email_service
from server.services.email import email_about_assignment, substitute_about_assignment
from server.services.email.templates import get_email, make_substitutions
from server.typings.enum import EmailTemplate

NAME = 'Lovelace, Ada & <Bo>'  # first name: "Ada & <Bo>"


@pytest.mark.parametrize('value', ['Jo\\hn', 'Ann \\1', '\\g<0>', 'C:\\new\\table'])
def test_values_with_backslashes_are_taken_literally(value):
    assert make_substitutions('Dear {{NAME}},', {'NAME': value}) == f'Dear {value},'


def test_placeholders_allow_spaces_inside_the_braces():
    assert make_substitutions('{{NAME}} / {{ NAME }}', {'NAME': 'Ada'}) == 'Ada / Ada'


def test_html_values_are_escaped():
    assert make_substitutions('<b>{{NAME}}</b>', {'NAME': 'Ada & <Bo>'}, html=True) == \
        '<b>Ada &amp; &lt;Bo&gt;</b>'


def test_plain_text_values_are_not_escaped():
    assert make_substitutions('Dear {{NAME}}', {'NAME': 'Ada & <Bo>'}) == 'Dear Ada & <Bo>'


def test_template_email_escapes_body_but_not_subject():
    email = get_email(EmailTemplate.ASSIGNMENT_INFORM_EMAIL, {'EXAM': 'Midterm <1> & 2'}, {'NAME': 'Ada & <Bo>'})
    assert email.body_html
    assert email.subject == 'Your Exam Seating Assignment for Midterm <1> & 2'
    assert 'Dear <strong>Ada &amp; &lt;Bo&gt;</strong>' in email.body


@pytest.fixture
def jimmy(seeded_db):
    exam = db.session.get(Exam, 1)
    exam.display_name = 'Midterm <1> & 2'
    jimmy = Student.query.filter_by(exam_id=exam.id, canvas_id='234567').one()
    jimmy.name = NAME
    db.session.commit()
    assert jimmy.assignment is not None
    yield jimmy


def _form(body_html):
    return EmailForm(formdata=None, data={
        'from_addr': 'staff@berkeley.edu', 'to_addr': 'x@berkeley.edu', 'subject': 'Seat for {{EXAM}}',
        'body': '<p>Dear {{NAME}}, {{EXAM}}</p>', 'body_html': body_html})


def test_substitution_escapes_an_html_body(jimmy):
    with flask_app.test_request_context():
        subject, body = substitute_about_assignment(jimmy.exam, _form(body_html=True), jimmy)
    assert subject == 'Seat for Midterm <1> & 2'
    assert body == '<p>Dear Ada &amp; &lt;Bo&gt;, Midterm &lt;1&gt; &amp; 2</p>'


def test_substitution_leaves_a_plain_body_alone(jimmy):
    with flask_app.test_request_context():
        _, body = substitute_about_assignment(jimmy.exam, _form(body_html=False), jimmy)
    assert body == '<p>Dear Ada & <Bo>, Midterm <1> & 2</p>'


@pytest.fixture
def sent(monkeypatch):
    """Captures the messages email_about_assignment would send."""
    sent_messages = []

    def fake_send_emails(*, smtp, messages):
        sent_messages.extend(messages)
        return [(message, None) for message in messages], []

    monkeypatch.setattr(email_service, 'send_emails', fake_send_emails)
    yield sent_messages


@pytest.mark.parametrize('body_html, content_types', [
    (True, ['text/plain', 'text/html']),
    (False, ['text/plain']),
])
def test_html_checkbox_decides_whether_an_html_part_is_sent(jimmy, sent, body_html, content_types):
    with flask_app.test_request_context():
        successful, failed = email_about_assignment(jimmy.exam, _form(body_html), [jimmy.email])
    assert successful == {jimmy.email} and not failed
    (message,) = sent
    parts = list(message.iter_parts()) if message.is_multipart() else [message]
    assert [part.get_content_type() for part in parts] == content_types
    if body_html:
        assert 'Dear Ada &amp; &lt;Bo&gt;' in parts[1].get_content()
    else:
        assert 'Dear Ada & <Bo>' in parts[0].get_content()
    assert message['Subject'] == 'Seat for Midterm <1> & 2'


def test_backslash_in_a_name_does_not_stop_the_emails(jimmy, sent):
    jimmy.name = 'Xu, Jo\\hn'
    db.session.commit()
    with flask_app.test_request_context():
        successful, _ = email_about_assignment(jimmy.exam, _form(True), [jimmy.email])
    assert successful == {jimmy.email}
    assert 'Dear Jo\\Hn' in sent[0].get_body(('html',)).get_content()
