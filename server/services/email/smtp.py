from flask import current_app
from smtplib import SMTP, SMTPException
from email.message import EmailMessage


class SMTPConfig:
    def __init__(self, smtp_server, smtp_port, username, password, use_tls=True, use_auth=True):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.use_auth = use_auth

    def __repr__(self) -> str:
        return (f'SMTPConfig(smtp_server={self.smtp_server}, '
                f'smtp_port={self.smtp_port}, '
                f'username={self.username}, '
                f'use_tls={self.use_tls}, '
                f'use_auth={self.use_auth})')


def send_emails(*, smtp: SMTPConfig, messages=list[EmailMessage]):
    successful_emails = []
    failed_emails = []
    for msg in messages:
        try:
            server = SMTP(smtp.smtp_server, smtp.smtp_port)
            # if server.has_extn('STARTTLS'):
            if smtp.use_tls:
                server.starttls()
            # if server.has_extn('AUTH'):
            if smtp.use_auth:
                server.login(smtp.username, smtp.password)
            server.send_message(msg)
            server.quit()
            successful_emails.append((msg, None))
        except SMTPException as e:
            err_msg = f"SMTP error occurred when sending email: {str(e)}\n Config: \n{smtp}"
            current_app.logger.error(err_msg)
            failed_emails.append((msg, err_msg))
        except Exception as e:
            err_msg = f"Error occurred when sending email: {str(e)}\n Config: \n{smtp}"
            current_app.logger.error(err_msg)
            failed_emails.append((msg, err_msg))
    return successful_emails, failed_emails


def construct_email(*, from_addr, to_addr, subject, body, body_html=None, bcc_addr=None, cc_addr=None):
    msg = EmailMessage()
    msg['From'], msg['To'], msg['Subject'] = from_addr, to_addr, subject
    if bcc_addr:
        if isinstance(bcc_addr, str):
            bcc_addr = bcc_addr.split(',')
        msg['Bcc'] = bcc_addr
    if cc_addr:
        if isinstance(cc_addr, str):
            cc_addr = cc_addr.split(',')
        msg['Cc'] = cc_addr
    msg.set_content(body)
    if body_html:
        msg.add_alternative(body_html, subtype='html')
    return msg


def send_single_email(*, smtp: SMTPConfig, from_addr, to_addr, subject, body,
                      body_html=None, bcc_addr=None, cc_addr=None):
    msg = construct_email(from_addr=from_addr, to_addr=to_addr, subject=subject, body=body,
                          body_html=body_html, bcc_addr=bcc_addr, cc_addr=cc_addr)
    successful_emails, failed_emails = send_emails(smtp=smtp, messages=[msg])
    if successful_emails:
        return successful_emails[0]
    if failed_emails:
        return failed_emails[0]
