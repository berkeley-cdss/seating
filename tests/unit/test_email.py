from unittest.mock import patch
import server.services.email.templates as templates
from server.services.email import send_email, _email_config
from server.typings.enum import EmailTemplate


@patch('server.services.email.smtp.SMTP')
def test_send_email(mock_smtp):
    test_email = \
        templates.get_email(EmailTemplate.ASSIGNMENT_INFORM_EMAIL,
                            {"EXAM": "test exam"},
                            {"NAME": "test name",
                                "COURSE": "test course",
                                "EXAM": "test exam",
                                "ROOM": "test room",
                                "SEAT": "test seat",
                                "URL": "test/url",
                                "ADDITIONAL_INFO": "test additional text",
                                "SIGNATURE": "test signature"})

    send_email(smtp=_email_config,
               from_addr="from@xyz.com",
               to_addr="to@xyz.com",
               subject=test_email.subject,
               body=test_email.body,
               body_html=test_email.body if test_email.body_html else None)

    # basic checks of the use of smtp server
    mock_smtp.assert_called_with(_email_config.smtp_server, _email_config.smtp_port)
    mock_smtp.return_value.starttls.assert_called_once()
    mock_smtp.return_value.login.assert_called_once_with(_email_config.username, _email_config.password)
    mock_smtp.return_value.send_message.assert_called_once()
    mock_smtp.return_value.quit.assert_called_once()

    # check the email content
    msg = mock_smtp.return_value.send_message.call_args[0][0]
    assert msg['From'] == "from@xyz.com"
    assert msg['To'] == "to@xyz.com"
    assert msg['Subject'] == test_email.subject
