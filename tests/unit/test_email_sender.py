"""
Every email goes out from the configured sender (EMAIL_SENDER), whatever the form says: the app sends
as the university account, so staff must not be able to send as anyone else. Staff set Reply-To instead.
"""
import re

import pytest

import server.services.email as email_service
from server.models import Student
from server.services.email.smtp import construct_email

pytestmark = pytest.mark.app_config(EMAIL_SENDER='seating@example.edu')

EMAIL_URL = '/offerings/1234567/exams/midterm1/students/email/'
BATCH_URL = '/offerings/1234567/exams/midterm1/students/email/send/'


@pytest.fixture
def sent(monkeypatch):
    """The messages the app sends, captured instead of going to an SMTP server."""
    sent_messages = []

    def fake_send_emails(*, smtp, messages):
        sent_messages.extend(messages)
        return [(message, None) for message in messages], []

    monkeypatch.setattr(email_service, 'send_emails', fake_send_emails)
    yield sent_messages


@pytest.fixture
def staff(seeded_db, login_as):
    return login_as(1)


@pytest.fixture
def jimmy(seeded_db):
    """The seed's one seated student."""
    return Student.query.filter_by(exam_id=1, canvas_id='234567').one()


def _post(client, url, **fields):
    page = client.get(EMAIL_URL).get_data(as_text=True)
    data = {'csrf_token': re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', page).group(1),
            'subject': 'Seat', 'body': 'Dear {{NAME}}', **fields}
    return client.post(url, data=data)


def test_students_get_the_email_from_the_sender_with_staffs_reply_to(staff, jimmy, sent):
    response = _post(staff, BATCH_URL, to_addr=jimmy.email, reply_to='cs61a@berkeley.edu')
    assert response.status_code == 200
    (message,) = sent
    assert message['From'] == 'seating@example.edu'
    assert message['Reply-To'] == 'cs61a@berkeley.edu'


def test_a_from_in_the_form_is_ignored(staff, jimmy, sent):
    _post(staff, BATCH_URL, to_addr=jimmy.email, from_addr='registrar@berkeley.edu')
    (message,) = sent
    assert message['From'] == 'seating@example.edu'
    assert 'registrar@berkeley.edu' not in message.as_string()


def test_a_test_email_comes_from_the_sender_too(staff, jimmy, sent):
    _post(staff, EMAIL_URL, send_test='y', test_student=str(jimmy.id), test_to_addr='me@berkeley.edu',
          from_addr='registrar@berkeley.edu', reply_to='cs61a@berkeley.edu')
    (message,) = sent
    assert (message['From'], message['Reply-To']) == ('seating@example.edu', 'cs61a@berkeley.edu')


def test_reply_to_is_optional(staff, jimmy, sent):
    response = _post(staff, BATCH_URL, to_addr=jimmy.email)
    assert response.status_code == 200
    (message,) = sent
    assert message['Reply-To'] is None


def test_reply_to_must_be_an_email_address(staff, jimmy, sent):
    response = _post(staff, BATCH_URL, to_addr=jimmy.email, reply_to='not an address')
    assert response.status_code == 400
    assert set(response.get_json()['errors']) == {'reply_to'}
    assert sent == []


def test_reply_to_is_a_single_address(staff, jimmy, sent):
    # a list would pass the field along to whoever it names, like CC does; one address is all it needs
    response = _post(staff, BATCH_URL, to_addr=jimmy.email, reply_to='a@berkeley.edu, b@berkeley.edu')
    assert response.status_code == 400
    assert sent == []


def test_the_page_shows_the_sender_and_takes_no_from(staff):
    page = staff.get(EMAIL_URL).get_data(as_text=True)
    from_input = re.search(r'<input[^>]*id="from_addr"[^>]*>', page, re.S).group(0)
    assert 'value="seating@example.edu"' in from_input
    assert 'readonly' in from_input and 'name=' not in from_input
    assert 'id="reply_to"' in page


def test_construct_email_leaves_out_an_empty_reply_to():
    message = construct_email(from_addr='seating@example.edu', to_addr='s@berkeley.edu', subject='Seat',
                              body='Your seat', reply_to='')
    assert message['Reply-To'] is None
