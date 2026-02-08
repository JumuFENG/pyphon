import os
import sys
import logging
import json
import base64
import random
from functools import lru_cache


class Config:
    @classmethod
    @lru_cache(maxsize=1)
    def _cfg_path(self):
        cpth = os.path.join(os.path.dirname(__file__), '../config/config.json')
        if not os.path.isdir(os.path.dirname(cpth)):
            os.mkdir(os.path.dirname(cpth))
        return cpth

    @classmethod
    @lru_cache(maxsize=None)
    def all_configs(self):
        cfg_path = self._cfg_path()
        allconfigs = None
        if not os.path.isfile(cfg_path):
            allconfigs = {
                "fha": {
                    "server": "",
                    "uemail": "",
                    "pwd": ""
                },
                "unp": {
                    "account": "",
                    "pwd": "",
                    "credit": False
                },
                "client": {
                    "log_level": "INFO",
                    "purchase_new_stocks": True,
                    "port": 5888,
                    "iunstrs": {
                    }
                }
            }
            self.save(allconfigs)
            return allconfigs

        with open(cfg_path, 'r') as f:
            allconfigs = json.load(f)

        bsave = False
        if not allconfigs['unp']['pwd'].startswith('*'):
            allconfigs['unp']['pwd'] = self.simple_encrypt(allconfigs['unp']['pwd'])
            bsave = True
        if 'pwd' in allconfigs['fha'] and not allconfigs['fha']['pwd'].startswith('*'):
            allconfigs['fha']['pwd'] = self.simple_encrypt(allconfigs['fha']['pwd'])
            bsave = True
        if bsave:
            self.save(allconfigs)

        return allconfigs

    @classmethod
    def save(self, cfg):
        cfg_path = self._cfg_path()
        with open(cfg_path, 'w') as f:
            json.dump(cfg, f, indent=4)

    @classmethod
    def simple_encrypt(self, txt):
        r = random.randint(1, 5)
        x = base64.b64encode(txt.encode('utf-8'))
        for i in range(r):
            x = base64.b64encode(x)
        return '*'*r + x.decode('utf-8')

    @classmethod
    def simple_decrypt(self, etxt):
        r = etxt.rfind('*')
        etxt = etxt[r:]
        x = base64.b64decode(etxt.encode('utf-8'))
        for i in range(r+1):
            x = base64.b64decode(x)
        return x.decode('utf-8')

    @classmethod
    def data_service(self):
        return self.all_configs()['fha']

    @classmethod
    def account(self):
        return self.all_configs()['unp']

    @classmethod
    def trade_config(self):
        return self.all_configs()['client']

    @classmethod
    def log_level(self):
        lvl = self.all_configs()['client'].get("log_level", "INFO").upper()
        return logging._nameToLevel[lvl]

    @classmethod
    def log_handler(self):
        handlers = self.all_configs().get('log_handler', ['file', 'stdout'])
        lhandlers = []
        if 'file' in handlers:
            lg_path = os.path.join(os.path.dirname(__file__), '../logs/emtrader.log')
            if not os.path.isdir(os.path.dirname(lg_path)):
                os.mkdir(os.path.dirname(lg_path))
            lhandlers.append(logging.FileHandler(lg_path))
        if any(x in handlers for x in ['stdout', 'console']):
            lhandlers.append(logging.StreamHandler(sys.stdout))
        return lhandlers


logging.basicConfig(
    level=Config.log_level(),
    format='%(levelname)s | %(asctime)s-%(filename)s@%(lineno)d<%(name)s> %(message)s',
    handlers=Config.log_handler(),
    force=True
)

logger: logging.Logger = logging.getLogger('pyphon')

