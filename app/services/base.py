import logging

from app.config.settings import Settings


class BaseService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings
        self.logger = logging.getLogger(self.__class__.__name__)

