from app.shared.exceptions import BusinessRuleError, NotFoundError, ValidationError


class ImportJobNotFoundError(NotFoundError):
    code = "IMPORT_NOT_FOUND"
    message = "Import job not found"


class ImportNotOpenError(BusinessRuleError):
    code = "IMPORT_NOT_OPEN"
    message = "That import has already finished and cannot be changed"


class UnreadableFileError(ValidationError):
    code = "UNREADABLE_FILE"
    message = "The file could not be read as a spreadsheet"


class NoHeaderRowError(ValidationError):
    code = "NO_HEADER_ROW"
    message = "The first row must contain the column names"


class UnknownTargetFieldError(ValidationError):
    code = "UNKNOWN_TARGET_FIELD"
    message = "That target field does not exist for this entity"


class MissingRequiredColumnsError(ValidationError):
    code = "MISSING_REQUIRED_COLUMNS"
    message = "Some required fields have no column mapped to them"


class ImportTooLargeError(ValidationError):
    code = "IMPORT_TOO_LARGE"
    message = "That file has more rows than a single import accepts"
