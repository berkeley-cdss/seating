import re
import itertools

from apiclient import errors
from server import app
from server.typings.exception import DataValidationError

from google.oauth2 import service_account
from googleapiclient.discovery import build

SERVICE_ACCOUNT_FILE = app.config.get('GOOGLE_SERVICE_ACCOUNT_CREDS_FILE_PATH')

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)

service = build('sheets', 'v4', credentials=credentials)


def _get_spreadsheet_id(sheet_url):
    m = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', sheet_url)
    if not m or not m.group(1):
        raise DataValidationError('Enter a Google Sheets URL')
    return m.group(1)


def get_spreadsheet_tabs(sheet_url):
    spreadsheet_id = _get_spreadsheet_id(sheet_url)
    try:
        sheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = sheet_metadata.get('sheets', '')
        return [sheet['properties']['title'] for sheet in sheets]
    except errors.HttpError as e:
        raise DataValidationError(e._get_reason())


def get_spreadsheet_tab_content(sheet_url, tab_name):
    spreadsheet_id = _get_spreadsheet_id(sheet_url)
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=tab_name).execute()
    except errors.HttpError as e:
        raise DataValidationError(e._get_reason())
    values = result.get('values', [])

    if not values:
        raise DataValidationError('Sheet is empty')
    headers = [h.lower() for h in values[0]]
    rows = [
        {k: v for k, v in itertools.zip_longest(headers, row, fillvalue='')}
        for row in values[1:]
    ]
    if len(set(headers)) != len(headers):
        raise DataValidationError('Headers must be unique')
    elif not all(re.match(r'[a-z0-9]+', h) for h in headers):
        raise DataValidationError('Headers must consist of digits and numbers')
    return headers, rows
