from app.shared.exceptions import BusinessRuleError, NotFoundError, ValidationError


class FileNotFoundError(NotFoundError):
    code = "FILE_NOT_FOUND"
    message = "File not found"


class FileTooLargeError(ValidationError):
    code = "FILE_TOO_LARGE"
    message = "That file exceeds the maximum upload size"


class UnsupportedFileTypeError(ValidationError):
    code = "UNSUPPORTED_FILE_TYPE"
    message = "That file type is not accepted"


class EmptyFileError(ValidationError):
    code = "EMPTY_FILE"
    message = "The uploaded file is empty"


class StorageUnavailableError(BusinessRuleError):
    code = "STORAGE_UNAVAILABLE"
    message = "The file store could not be reached"
    status_code = 503
