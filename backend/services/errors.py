"""API errors. Every error response is {"error": {"code", "message"}}."""

STATUS = {"NOT_FOUND": 404, "BAD_REQUEST": 400, "UNAUTHORIZED": 401, "FORBIDDEN": 403, "CONFLICT": 409,
          "INSUFFICIENT_QUANTITY": 409, "GONE": 410, "NO_TEXT_LAYER": 422, "UNSUPPORTED_FILE": 415, "TRAFFIC_UNAVAILABLE": 503, "GEMINI_UNAVAILABLE": 503, "DB_UNAVAILABLE": 503, "INTERNAL": 500}


class ApiError(Exception):
    def __init__(self, code, message, status=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status or STATUS.get(code, 400)

    def body(self):
        return {"error": {"code": self.code, "message": self.message}}


def not_found(kind, id_):
    return ApiError("NOT_FOUND", f"{kind} {id_} does not exist")


def bad_request(message):
    return ApiError("BAD_REQUEST", message)


def forbidden(message="You can only change your own company's records"):
    return ApiError("FORBIDDEN", message)


def unauthorized():
    return ApiError("UNAUTHORIZED", "Select a company first")


def db_unavailable():
    return ApiError("DB_UNAVAILABLE", "The database is not connected. Marketplace, messaging and assistant actions are "
                                      "unavailable; the map, overlaps and export still work.")


def gemini_unavailable(message="Gemini is not responding. Try again in a moment."):
    return ApiError("GEMINI_UNAVAILABLE", message)
