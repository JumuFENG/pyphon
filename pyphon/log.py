import logging
import sys


class phonloger:
    def __init__(self):
        self._logger = None

    def _init_logger(self):
        if self._logger is None:
            self._logger = logging.getLogger('pyphon')
            
            # 如果logger还没有handler，添加一个
            if not self._logger.handlers:
                handler = logging.StreamHandler(sys.stdout)
                formatter = logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                )
                handler.setFormatter(formatter)
                self._logger.addHandler(handler)
                self._logger.setLevel(logging.INFO)

    def __getattr__(self, name):
        self._init_logger()
        return getattr(self._logger, name)

logger: logging.Logger = phonloger()
