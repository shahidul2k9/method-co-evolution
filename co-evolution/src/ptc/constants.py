from enum import Enum

class MethodChangeType(str, Enum):
    INTRODUCTION = "Yintroduced"
    MOVE = "Ymovefromfile"
    BODY = "Ybodychange"
    DOCUMENTATION = "Ydocumentationchange"
    FILE_MOVE = "Yfilerename"
    RENAME = "Yrename"
    MODIFIER = "Ymodifierchange"
    RETURN_TYPE = "Yreturntypechange"
    EXCEPTION = "Yexceptionschange"
    PARAMETER = "Yparameterchange"
    PARAMETER_META = "Yparametermetachange" # find out what this is
    ANNOTATION = "Yannotationchnage"
    FORMAT = "Yformatchange"
    MULTI = "Ymultichange"

class LinkStrategy(str, Enum):
    MAX = "max"
    LAST_CALL = "lc"
CODE_SHOVEL_UNSUPPORTED_CHANGES = [MethodChangeType.DOCUMENTATION, MethodChangeType.ANNOTATION, MethodChangeType.FORMAT]
ALL_REPOSITORY = "All Project"