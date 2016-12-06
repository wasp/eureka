from http import HTTPStatus


class EurekaException(Exception):
    def __init__(self, status: HTTPStatus, *args, **kwargs):
        self._status = status
        super().__init__(*args, **kwargs)

    @property
    def status(self) -> HTTPStatus:
        return self._status
