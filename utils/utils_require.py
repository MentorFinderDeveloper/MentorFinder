from functools import wraps

from utils.utils_request import request_failed

# Generic fallback used by check_length()/require() when no field-specific
# limit is supplied. Field inputs should use the dedicated constants below.
MAX_CHAR_LENGTH = 255

# Per-field input length limits (in characters). These mirror the frontend
# ONE-TO-ONE (see frontend/src/constants/inputLimits.ts): every INPUT_LIMITS
# key has a MAX_<KEY>_LENGTH constant here with the same value. The frontend
# maxLength warns the user before submitting; the server enforces these as the
# source of truth. Keep both files in sync.

# 账号相关 / account
MAX_USERNAME_LENGTH = 20            # INPUT_LIMITS.USERNAME
MAX_EMAIL_LENGTH = 40               # INPUT_LIMITS.EMAIL
MAX_PASSWORD_LENGTH = 64            # INPUT_LIMITS.PASSWORD
MAX_VERIFICATION_CODE_LENGTH = 6    # INPUT_LIMITS.VERIFICATION_CODE

# 个人主页 / 资料 / profile
MAX_SIGNATURE_LENGTH = 100          # INPUT_LIMITS.SIGNATURE
MAX_AVATAR_URL_LENGTH = 100         # INPUT_LIMITS.AVATAR_URL
MAX_LONG_TEXT_LENGTH = 1000         # INPUT_LIMITS.LONG_TEXT (intro/experience/honors/projects)

# 导师 / 论文 / mentor & paper
MAX_NAME_LENGTH = 20                # INPUT_LIMITS.NAME (mentor names, submitted real name)
MAX_RESEARCH_DIRECTION_LENGTH = 200  # INPUT_LIMITS.RESEARCH_DIRECTION
MAX_MENTOR_PROFILE_LENGTH = 1000    # INPUT_LIMITS.MENTOR_PROFILE
MAX_PAPER_TITLE_LENGTH = 200        # INPUT_LIMITS.PAPER_TITLE
MAX_PAPER_ABSTRACT_LENGTH = 3000    # INPUT_LIMITS.PAPER_ABSTRACT
MAX_AUTHOR_NAMES_LENGTH = 1000      # INPUT_LIMITS.AUTHOR_NAMES

# 搜索 / 过滤关键词 / search
MAX_KEYWORD_LENGTH = 200            # INPUT_LIMITS.KEYWORD


def check_length(value, key, max_length=MAX_CHAR_LENGTH, err_code=-2):
    """Ensure a string value does not exceed `max_length` characters.

    Raises KeyError so the surrounding `@CheckRequire` decorator converts it
    into an HTTP 400 response, matching the project's existing validation
    style. Returns the value unchanged when it is within the limit (or None).
    """
    if value is not None and len(value) > max_length:
        raise KeyError(
            f"Invalid parameters. [{key}] is too long (max {max_length} characters)",
            err_code,
        )
    return value


# A decorator function for processing `require` in view function.
def CheckRequire(check_fn):
    @wraps(check_fn)
    def decorated(*args, **kwargs):
        try:
            return check_fn(*args, **kwargs)
        except Exception as e:
            # Handle exception e
            error_code = -2 if len(e.args) < 2 else e.args[1]
            return request_failed(error_code, e.args[0], 400)  # Refer to below
    return decorated


# Here err_code == -2 denotes "Error in request body"
# And err_code == -1 denotes "Error in request URL parsing"
def require(body, key, type="string", err_msg=None, err_code=-2, max_length=None):

    if key not in body.keys():
        raise KeyError(err_msg if err_msg is not None 
                       else f"Invalid parameters. Expected `{key}`, but not found.", err_code)
    
    val = body[key]
    
    err_msg = f"Invalid parameters. Expected `{key}` to be `{type}` type."\
                if err_msg is None else err_msg
    
    if type == "int":
        try:
            val = int(val)
            return val
        except:
            raise KeyError(err_msg, err_code)
    
    elif type == "float":
        try:
            val = float(val)
            return val
        except:
            raise KeyError(err_msg, err_code)
    
    elif type == "string":
        try:
            val = str(val)
        except:
            raise KeyError(err_msg, err_code)
        if max_length is not None and len(val) > max_length:
            raise KeyError(
                f"Invalid parameters. [{key}] is too long (max {max_length} characters)",
                err_code,
            )
        return val
    
    elif type == "list":
        try:
            assert isinstance(val, list)
            return val
        except:
            raise KeyError(err_msg, err_code)

    else:
        raise NotImplementedError(f"Type `{type}` not implemented.", err_code)