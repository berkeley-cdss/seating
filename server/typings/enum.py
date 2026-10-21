from enum import Enum


class AppEnvironment(Enum):
    DEVELOPMENT = 'development'
    PRODUCTION = 'production'
    STAGING = 'staging'
    TESTING = 'testing'


class EmailTemplate(Enum):
    ASSIGNMENT_INFORM_EMAIL = 'assignment_inform_email'


class GcpSaCredType(Enum):
    FILE = 'file'  # a service account key file, at GCP_SA_CRED_FILE
    ENV = 'env'  # a service account key, base64-encoded in GCP_SA_CRED_VALUE
    RUNTIME = 'runtime'  # no key: the account the app runs as (on Cloud Run, the service's own account)


class AssignmentImportStrategy(Enum):
    IGNORE = 'ignore'
    REVALIDATE = 'revalidate'
    FORCE = 'force'


class NewRowImportStrategy(Enum):
    IGNORE = 'ignore'  # ignore new rows (unseen canvas id)
    APPEND = 'append'  # append new rows into list


class UpdatedRowImportStrategy(Enum):
    IGNORE = 'ignore'  # ignore updated rows (seen canvas id)
    MERGE = 'merge'  # try mergin info (if blank, then use old info)
    OVERWRITE = 'overwrite'  # use new info (if blank, then make blank)


class MissingRowImportStrategy(Enum):
    IGNORE = 'ignore'  # ignore missing rows (seen canvas id)
    DELETE = 'delete'  # remove missing rows
