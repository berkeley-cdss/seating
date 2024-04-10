from flask import current_app
from smtplib import SMTP, SMTPException
from email.message import EmailMessage
from time import sleep


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


def construct_smtp_server(smtp: SMTPConfig):
    try:
        smtp_server = SMTP(smtp.smtp_server, smtp.smtp_port)
        if smtp.use_tls:
            smtp_server.starttls()
        if smtp.use_auth:
            smtp_server.login(smtp.username, smtp.password)
    except Exception as e:
        current_app.logger.error(f"Error occurred when connecting to SMTP server: {str(e)}\nConfig:\n{smtp}")
        return None
    return smtp_server


def send_email_batch(*, smtp_server: SMTP, batch=list[EmailMessage],
                     max_retries=3, retry_delay=1.0, exponential_backoff=True):
    successful_emails = []
    failed_emails = []
    for msg in batch:
        for attempt in range(max_retries):
            try:
                smtp_server.send_message(msg)
                successful_emails.append((msg, None))
                break
            except Exception as e:
                current_app.logger.error(
                    f"Error on attempt {attempt + 1} for email to {msg['To']}: {str(e)}")
                if attempt < max_retries - 1:
                    cur_delay = retry_delay * (2 ** attempt) if exponential_backoff else retry_delay
                    sleep(cur_delay)
                else:
                    err_msg = f"SMTP error after {max_retries} retries for email to {msg['To']}: {str(e)}"
                    failed_emails.append((msg, err_msg))
    return successful_emails, failed_emails


def send_emails(*, smtp: SMTPConfig, messages=list[EmailMessage],
                batch_size=100, batch_delay=0.1,
                max_retries=3, retry_delay=1.0, exponential_backoff=True):
    successful_emails = []
    failed_emails = []

    smtp_server = construct_smtp_server(smtp)
    if not smtp_server:
        failed_emails = [(msg, "Error occurred when connecting to SMTP server") for msg in messages]
        return successful_emails, failed_emails

    try:
        for i in range(0, len(messages), batch_size):
            batch = messages[i:i + batch_size]
            successful_batch, failed_batch = send_email_batch(
                smtp_server=smtp_server, batch=batch,
                max_retries=max_retries, retry_delay=retry_delay, exponential_backoff=exponential_backoff)
            successful_emails.extend(successful_batch)
            failed_emails.extend(failed_batch)
            sleep(batch_delay)
    except Exception as e:
        err_msg = f"Error occurred when sending emails: {str(e)} (Batch number: {i})\n Config: \n{smtp}"
        current_app.logger.error(err_msg)
        # everything that is not reached is considered failed
        already_categorized = set([msg for msg, _ in successful_emails + failed_emails])
        for msg in messages:
            if msg not in already_categorized:
                failed_emails.append((msg, err_msg))
    finally:
        try:
            smtp_server.quit()
        except Exception as e:
            err_msg = f"Error occurred when closing SMTP server: {str(e)}\n Config: \n{smtp}"
            current_app.logger.error(err_msg)
    return successful_emails, failed_emails


def send_single_email(*, smtp: SMTPConfig, from_addr, to_addr, subject, body,
                      body_html=None, bcc_addr=None, cc_addr=None):
    msg = construct_email(from_addr=from_addr, to_addr=to_addr, subject=subject, body=body,
                          body_html=body_html, bcc_addr=bcc_addr, cc_addr=cc_addr)
    successful_emails, failed_emails = send_emails(smtp=smtp, messages=[msg])
    if successful_emails:
        return successful_emails[0]
    if failed_emails:
        return failed_emails[0]
