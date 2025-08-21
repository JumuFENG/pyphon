#!/usr/bin/env python3
"""
EMTrader Web界面启动脚本
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'pyphon'))

from pyphon.emtrader import start_server

if __name__ == '__main__':
    start_server()
