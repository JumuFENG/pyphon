import json
import os
import base64
import random
from functools import lru_cache


class Config:
    @classmethod
    @lru_cache(maxsize=None)
    def all_configs(self):
        cfg_path = os.path.join(os.path.dirname(__file__), '../config/config.json')
        if not os.path.isdir(os.path.dirname(cfg_path)):
            os.mkdir(os.path.dirname(cfg_path))
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
                    "purchase_new_stocks": True,
                    "port": 5888,
                    "iunstrs": {
                    }
                }
            }
            self._save(cfg_path, allconfigs)
            return allconfigs

        with open(cfg_path, 'r') as f:
            allconfigs = json.load(f)

        bsave = False
        if not allconfigs['unp']['pwd'].startswith('*'):
            allconfigs['unp']['pwd'] = self.simple_encrypt(allconfigs['unp']['pwd'])
            bsave = True
        if not allconfigs['fha']['pwd'].startswith('*'):
            allconfigs['fha']['pwd'] = self.simple_encrypt(allconfigs['fha']['pwd'])
            bsave = True
        if bsave:
            self._save(cfg_path, allconfigs)

        return allconfigs

    @classmethod
    def _save(self, cfg_path, cfg):
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
