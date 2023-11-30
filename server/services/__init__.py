import re
import itertools

from apiclient import discovery, errors

from server.services.auth import google_oauth
from server.typings.exception import DataValidationError

DISCOVERY_URL = ('https://sheets.googleapis.com/$discovery/rest?'
                 'version=v4')


def _get_spreadsheet_id(sheet_url):
    m = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', sheet_url)
    if not m or not m.group(1):
        raise DataValidationError('Enter a Google Sheets URL')
    return m.group(1)


def _get_spreadsheet_service(sheet_url):
    return discovery.build('sheets', 'v4', http=google_oauth.http(),
                           discoveryServiceUrl=DISCOVERY_URL)


def get_spreadsheet_tabs(sheet_url):
    spreadsheet_id = _get_spreadsheet_id(sheet_url)
    service = _get_spreadsheet_service(sheet_url)
    try:
        sheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = sheet_metadata.get('sheets', '')
        return [sheet['properties']['title'] for sheet in sheets]
    except errors.HttpError as e:
        raise DataValidationError(e._get_reason())


def get_spreadsheet_tab_content(sheet_url, tab_name):
    spreadsheet_id = _get_spreadsheet_id(sheet_url)
    service = _get_spreadsheet_service(sheet_url)
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
