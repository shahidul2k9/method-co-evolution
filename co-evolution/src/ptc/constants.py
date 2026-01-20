from enum import Enum

class MethodChangeType(str, Enum):
    INTRODUCTION = "introduction"
    MOVE = "move"
    BODY = "body"
    REMOVE = "remove"
    DOCUMENTATION = "documentation"
    FILE_MOVE = "file_move"
    RENAME = "rename"
    MODIFIER = "modifier"
    RETURN_TYPE = "return_type"
    EXCEPTION = "exception"
    PARAMETER = "parameter"
    ANNOTATION = "annotation"
    FORMAT = "format"
