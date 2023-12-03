import csv
import io


def parse_csv(file):
    """
    Parse a CSV file and return a list of headers and rows.
    """
    reader = csv.DictReader(io.StringIO(file.read().decode('utf-8')))
    headers = list(reader.fieldnames)
    rows = [row for row in reader]
    return headers, rows
