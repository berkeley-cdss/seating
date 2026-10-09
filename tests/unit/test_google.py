import base64
import json
import unittest
from unittest.mock import ANY, MagicMock, patch

from apiclient import errors

from server import app
from server.services import google
from server.typings.exception import GcpError

SHEET_URL = 'https://docs.google.com/spreadsheets/d/abc-123_XYZ/edit'


class TestGetSpreadsheetService(unittest.TestCase):
    """Tests building the Sheets client from each credential type."""

    def setUp(self):
        google._get_spreadsheet_service.cache_clear()

    def tearDown(self):
        google._get_spreadsheet_service.cache_clear()

    @patch('server.services.google.build')
    @patch('server.services.google.service_account.Credentials')
    def test_file_credentials(self, mock_creds, mock_build):
        with patch.dict(app.config, {'GCP_SA_CRED_TYPE': 'file', 'GCP_SA_CRED_FILE': 'sa.json'}):
            service = google._get_spreadsheet_service()
        mock_creds.from_service_account_file.assert_called_once_with('sa.json', scopes=ANY)
        mock_build.assert_called_once_with(
            'sheets', 'v4', credentials=mock_creds.from_service_account_file.return_value)
        self.assertIs(service, mock_build.return_value)

    @patch('server.services.google.build')
    @patch('server.services.google.service_account.Credentials')
    def test_env_credentials(self, mock_creds, mock_build):
        info = {'type': 'service_account'}
        encoded = base64.b64encode(json.dumps(info).encode()).decode()
        with patch.dict(app.config, {'GCP_SA_CRED_TYPE': 'env', 'GCP_SA_CRED_VALUE': encoded}):
            google._get_spreadsheet_service()
        mock_creds.from_service_account_info.assert_called_once_with(info, scopes=ANY)

    def test_invalid_cred_type(self):
        with patch.dict(app.config, {'GCP_SA_CRED_TYPE': 'bogus'}):
            with self.assertRaisesRegex(GcpError, 'Invalid GCP_SA_CRED_TYPE'):
                google._get_spreadsheet_service()

    @patch('server.services.google.build')
    @patch('server.services.google.service_account.Credentials')
    def test_missing_credentials(self, mock_creds, mock_build):
        mock_creds.from_service_account_file.return_value = None
        with patch.dict(app.config, {'GCP_SA_CRED_TYPE': 'file'}):
            with self.assertRaisesRegex(GcpError, 'Invalid GCP credentials'):
                google._get_spreadsheet_service()
        mock_build.assert_not_called()

    @patch('server.services.google.build')
    @patch('server.services.google.service_account.Credentials')
    def test_service_is_cached(self, mock_creds, mock_build):
        with patch.dict(app.config, {'GCP_SA_CRED_TYPE': 'file'}):
            first = google._get_spreadsheet_service()
            second = google._get_spreadsheet_service()
        self.assertIs(first, second)
        mock_build.assert_called_once()


def _http_error():
    return errors.HttpError(MagicMock(status=403, reason='Forbidden'), b'')


class TestSpreadsheetReads(unittest.TestCase):
    """Tests reading tabs and tab content through a mocked Sheets client."""

    def setUp(self):
        patcher = patch('server.services.google._get_spreadsheet_service')
        self.spreadsheets = patcher.start().return_value.spreadsheets.return_value
        self.addCleanup(patcher.stop)

    def _set_values(self, values):
        self.spreadsheets.values.return_value.get.return_value.execute.return_value = {'values': values}

    def test_invalid_url(self):
        with self.assertRaisesRegex(GcpError, 'Google Sheets URL'):
            google.get_spreadsheet_tabs('https://example.com/not-a-sheet')

    def test_get_tabs(self):
        self.spreadsheets.get.return_value.execute.return_value = {
            'sheets': [{'properties': {'title': 'Rooms'}}, {'properties': {'title': 'Seats'}}]
        }
        self.assertEqual(google.get_spreadsheet_tabs(SHEET_URL), ['Rooms', 'Seats'])
        self.spreadsheets.get.assert_called_once_with(spreadsheetId='abc-123_XYZ')

    def test_get_tabs_http_error(self):
        self.spreadsheets.get.return_value.execute.side_effect = _http_error()
        with self.assertRaises(GcpError):
            google.get_spreadsheet_tabs(SHEET_URL)

    def test_get_tab_content(self):
        self._set_values([['Row', 'Seat'], ['A', '1'], ['B']])
        headers, rows = google.get_spreadsheet_tab_content(SHEET_URL, 'Seats')
        self.assertEqual(headers, ['row', 'seat'])
        self.assertEqual(rows, [{'row': 'A', 'seat': '1'}, {'row': 'B', 'seat': ''}])
        self.spreadsheets.values.return_value.get.assert_called_once_with(
            spreadsheetId='abc-123_XYZ', range='Seats')

    def test_get_tab_content_http_error(self):
        self.spreadsheets.values.return_value.get.return_value.execute.side_effect = _http_error()
        with self.assertRaises(GcpError):
            google.get_spreadsheet_tab_content(SHEET_URL, 'Seats')

    def test_get_tab_content_empty(self):
        self._set_values([])
        with self.assertRaisesRegex(GcpError, 'Sheet is empty'):
            google.get_spreadsheet_tab_content(SHEET_URL, 'Seats')

    def test_get_tab_content_duplicate_headers(self):
        self._set_values([['row', 'Row']])
        with self.assertRaisesRegex(GcpError, 'Headers must be unique'):
            google.get_spreadsheet_tab_content(SHEET_URL, 'Seats')

    def test_get_tab_content_invalid_headers(self):
        self._set_values([['row', '!!']])
        with self.assertRaisesRegex(GcpError, 'Headers must consist'):
            google.get_spreadsheet_tab_content(SHEET_URL, 'Seats')
