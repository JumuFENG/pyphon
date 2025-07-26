import os
import sys
import logging

lg_path = os.path.join(os.path.dirname(__file__), '../logs/emtrader.log')
if not os.path.isdir(os.path.dirname(lg_path)):
    os.mkdir(os.path.dirname(lg_path))
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s | %(asctime)s-%(filename)s@%(lineno)d<%(name)s> %(message)s',
    handlers=[logging.FileHandler(lg_path), logging.StreamHandler(sys.stdout)],
    force=True
)

logger: logging.Logger = logging.getLogger('pyphon')
