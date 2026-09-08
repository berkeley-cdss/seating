import csv
import io


class LowerCaseDictReader(csv.DictReader):
    """
    Custom CSV DictReader that converts all headers to lowercase first.
    """

    def __init__(self, *args, **kwargs):
        super(LowerCaseDictReader, self).__init__(*args, **kwargs)
        self.fieldnames = [field.lower() for field in self.fieldnames]


def parse_csv(file):
    """
    Parse a CSV file and return a list of headers and rows.
    """
    return parse_csv_str(file.read().decode('utf-8'))


def parse_csv_str(csv_str):
    """
    Parse a CSV string and return a list of headers and rows.
    """
    reader = LowerCaseDictReader(io.StringIO(csv_str))
    headers = list(reader.fieldnames)
    rows = [row for row in reader]
    return headers, rows


def original_csv_headers(csv_str):
    """
    The header row exactly as written, before parse_csv_str lowercases it.

    Useful when a column name is data - a layout is named by whoever made the
    spreadsheet, so it should be shown the way they spelled it.
    """
    return next(csv.reader(io.StringIO(csv_str)), [])


def to_csv_str(headers, rows) -> str:
    """
    Convert a list of headers and rows to a CSV string.
    """
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return output.getvalue()
