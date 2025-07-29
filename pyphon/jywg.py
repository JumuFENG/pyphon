import rsa
import base64
import random
import requests
import re
from functools import lru_cache, cached_property
import importlib.util
if importlib.util.find_spec("ddddocr"):
    from ddddocr import DdddOcr
from misc import join_url
from lofig import logger, Config


class jywg:
    def __init__(self, account, pwd, credit=False, active_time=30):
        self.session = requests.session()
        self.session.headers.update({
            "User-Agent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:138.0) Gecko/20100101 Firefox/138.0',
            'Connection': 'keep-alive',
        })
        self.jywg = 'https://jywg.eastmoneysec.com'
        self.myuserid = account
        self.mypassword = pwd
        self.keep_active = active_time
        self.margin_trade = credit
        self.basejs = None
        self.validate_key = None
        self.mxretry = 5

    @lru_cache(maxsize=1)
    def load_page(self):
        rsp = self.session.get(self.jywg)
        bjsreg = re.compile('<script src="(/JsBundles/BaseJS.*)"></script>')
        match = bjsreg.search(rsp.text)
        self.basejs = self.jywg + (match.group(1) if match else '/JsBundles/BaseJS')

    @cached_property
    def rand_num(self) -> str:
        """随机数属性，可以通过清除缓存"""
        return str(random.random())

    @property
    def vcodeurl(self):
        if hasattr(self, 'rand_num'):
            del self.rand_num
        return 'https://jywg.eastmoneysec.com/Login/YZM?randNum=' + self.rand_num

    @cached_property
    def ocr(self):
        if importlib.util.find_spec("ddddocr"):
            return DdddOcr(show_ad=False)
        return None

    def get_refreshed_vcode(self):
        rsp = self.session.get(self.vcodeurl)
        vcode = ''
        if self.ocr:
            vcode = self.ocr.classification(rsp.content)
        else:
            url = join_url(Config.data_service()['server'], 'api/captcha')
            data = {'img': base64.b64encode(rsp.content).decode('utf-8')}
            r = requests.post(url, data=data)
            r.raise_for_status()
            vcode = r.text.strip()

        if len(vcode) != 4:
            return self.get_refreshed_vcode()

        replace_map = {
            'g': '9', 'Q': '0', 'i': '1', 'D': '0', 'C': '0', 'u': '0',
            'U': '0', 'z': '7', 'Z': '7', 'c': '0', 'o': '0', 'q': '9'
        }
        fvcode = ''
        for c in vcode:
            if c.isdigit():
                fvcode += c
                continue
            if c in replace_map:
                fvcode += replace_map[c]
            else:
                return self.get_refreshed_vcode()
        return fvcode

    @cached_property
    def public_key(self) -> str:
        if self.basejs is None:
            self.load_page()
        rsp = self.session.get(self.basejs)
        reg = re.compile(r'setPublicKey\("(-----BEGIN PUBLIC KEY-----\\n.+?\\n-----END PUBLIC KEY-----)"')
        match = reg.search(rsp.text)
        if match:
            return match.group(1).replace('\\n', '\n')

        return (
            "-----BEGIN PUBLIC KEY-----\n"
            "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDHdsyxT66pDG4p73yope7jxA92\n"
            "c0AT4qIJ/xtbBcHkFPK77upnsfDTJiVEuQDH+MiMeb+XhCLNKZGp0yaUU6GlxZdp\n"
            "+nLW8b7Kmijr3iepaDhcbVTsYBWchaWUXauj9Lrhz58/6AE/NF0aMolxIGpsi+ST\n"
            "2hSHPu3GSXMdhPCkWQIDAQAB\n-----END PUBLIC KEY-----")

    def encrypted_pwd(self):
        pub_key = rsa.PublicKey.load_pkcs1_openssl_pem(self.public_key.encode('utf-8'))
        encrypted = rsa.encrypt(Config.simple_decrypt(self.mypassword).encode('utf-8'), pub_key)
        return base64.b64encode(encrypted).decode('utf-8')

    @property
    def login_url(self):
        return join_url(self.jywg, '/Login/Authentication')

    @property
    def trade_page(self):
        return join_url(self.jywg, '/MarginTrade/Buy' if self.margin_trade else '/Trade/Buy')

    def validate(self):
        if not self.myuserid:
            logger.error("请提供资金账号")
            return False

        if not re.match(r'^[0-9]{12}$', self.myuserid):
            logger.error("资金账号不合法")
            return False

        if not self.mypassword:
            logger.error("请提供交易密码")
            return False

        retry = 0
        while retry < self.mxretry:
            data = {
                'userId': self.myuserid,
                'password': self.encrypted_pwd(),
                'identifyCode': self.get_refreshed_vcode(),
                'randNumber': self.rand_num,
                'duration': str(self.keep_active),
                'authCode': "",
                'type': "Z"
            }

            logger.info(f"第{retry+1}次尝试登录:...")

            try:
                r = self.session.post(self.login_url, data)
                r.raise_for_status()  # 确保请求成功

                result = r.json()

                # 处理登录响应
                if result.get('Status') == 0:
                    logger.info("登录成功")
                    return self.fetch_validate_key()
                else:
                    if result.get('ErrCode') == -1:
                        logger.error(f"登录失败: {result.get('Message', '未知错误')}")
                        retry += 1
                    elif result.get('ErrCode') == -3:
                        logger.error("需要安全验证")
                        return False
                    elif result.get('ErrCode') == -11:
                        logger.error("需要短信验证")
                        return False
                    else:
                        logger.error(f"登录失败: {result.get('Message', '未知错误')}")
                        retry += 1

            except Exception as e:
                logger.error(f"登录请求异常: {str(e)}")
                return False

        logger.error(f'登录失败! 已达最大重试次数{self.mxretry}')
        return False

    def fetch_validate_key(self):
        """
        登录成功后跳转到交易页面并获取验证密钥
        """
        try:
            logger.info(f"获取验证密钥...")
            r = self.session.get(self.trade_page)
            r.raise_for_status()

            # 提取验证密钥
            reg = re.compile(r'<input\s+id="em_validatekey".*value="([^"]+)"')
            match = reg.search(r.text)
            if match:
                self.validate_key = match.group(1)
                logger.info(f"获取验证密钥成功: {self.validate_key[:8]}...{self.validate_key[-4:]}")
                return True
            else:
                logger.error("未找到验证密钥")
                return False

        except Exception as e:
            logger.error(f"跳转到交易页面失败: {str(e)}")
            return False


