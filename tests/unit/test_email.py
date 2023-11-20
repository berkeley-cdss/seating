import pytest
from unittest.mock import patch
import server.services.email.templates as templates
from server.services.email import send_email, _email_config, SMTPConfig
from server.typings.enum import EmailTemplate
from email.message import Message

TEST_FROM_EMAIL = 'sender@example.com'
TEST_TO_EMAIL = 'recipient@example.com'
TEST_SUBJECT = 'Test Subject'
TEST_BODY = 'Test Body'
TEST_BODY_HTML = '<html><body><h1>Test Body</h1></body></html>'


def get_content(msg: Message, type='text/html'):
    if msg.is_multipart():
        for part in msg.get_payload():
            if part.get_content_type() == type:
                return part.get_payload(decode=True).decode(part.get_content_charset())
    else:
        if msg.get_content_type() == type:
            return msg.get_payload(decode=True).decode(msg.get_content_charset())
    return None


@patch('server.services.email.smtp.SMTP')
def test_send_plain_text_email(mock_smtp):

    success = send_email(smtp=_email_config,
                         from_addr=TEST_FROM_EMAIL,
                         to_addr=TEST_TO_EMAIL,
                         subject=TEST_SUBJECT,
                         body=TEST_BODY)

    assert success

    # check the use of smtp server
    mock_smtp.assert_called_with(_email_config.smtp_server, _email_config.smtp_port)
    mock_smtp.return_value.starttls.assert_called_once()
    mock_smtp.return_value.login.assert_called_once_with(_email_config.username, _email_config.password)
    mock_smtp.return_value.send_message.assert_called_once()
    mock_smtp.return_value.quit.assert_called_once()

    # check email meta
    msg = mock_smtp.return_value.send_message.call_args[0][0]
    assert msg['From'] == TEST_FROM_EMAIL
    assert msg['To'] == TEST_TO_EMAIL
    assert msg['Subject'] == TEST_SUBJECT

    # check plain text content
    assert TEST_BODY in msg.get_payload()


@patch('server.services.email.smtp.SMTP')
def test_send_html_email(mock_smtp):

    success = send_email(smtp=_email_config,
                         from_addr=TEST_FROM_EMAIL,
                         to_addr=TEST_TO_EMAIL,
                         subject=TEST_SUBJECT,
                         body=TEST_BODY,
                         body_html=TEST_BODY_HTML)

    assert success

    msg = mock_smtp.return_value.send_message.call_args[0][0]
    html = get_content(msg, 'text/html')
    assert html is not None
    assert TEST_BODY_HTML in html


import threading  # noqa
from aiosmtpd.controller import Controller  # noqa
from aiosmtpd.handlers import Message as MessageHandler  # noqa
from email import message_from_string  # noqa


class CustomMessageHandler(MessageHandler):
    received_message = None

    def handle_message(self, message):
        CustomMessageHandler.received_message = message_from_string(message.as_string())


@pytest.fixture()
def smtp_server():
    controller = Controller(CustomMessageHandler(), hostname='localhost', port=1025)
    thread = threading.Thread(target=controller.start)
    thread.start()

    yield controller

    controller.stop()
    thread.join()


def test_send_plain_text_email_with_mock_smtp_server(smtp_server):
    smtp_config = SMTPConfig(smtp_server.hostname, smtp_server.port, "user", "pass")

    success = send_email(
        smtp=smtp_config,
        from_addr=TEST_FROM_EMAIL,
        to_addr=TEST_TO_EMAIL,
        subject=TEST_SUBJECT,
        body=TEST_BODY)

    assert success

    msg = CustomMessageHandler.received_message
    CustomMessageHandler.received_message = None

    assert msg is not None
    assert msg['From'] == TEST_FROM_EMAIL
    assert msg['To'] == TEST_TO_EMAIL
    assert msg['Subject'] == TEST_SUBJECT
    assert TEST_BODY in msg.get_payload()


def test_send_html_email_with_mock_smtp_server(smtp_server):
    smtp_config = SMTPConfig(smtp_server.hostname, smtp_server.port, "user", "pass")

    success = send_email(
        smtp=smtp_config,
        from_addr=TEST_FROM_EMAIL,
        to_addr=TEST_TO_EMAIL,
        subject=TEST_SUBJECT,
        body=TEST_BODY,
        body_html=TEST_BODY_HTML)

    assert success

    msg = CustomMessageHandler.received_message
    CustomMessageHandler.received_message = None

    # check html content
    html = get_content(msg, 'text/html')
    assert html is not None
    assert TEST_BODY_HTML in html
