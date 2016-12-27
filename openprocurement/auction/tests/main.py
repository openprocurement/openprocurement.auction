# -*- coding: utf-8 -*-

from gevent import monkey
monkey.patch_all()
import os.path
from robot import run_cli
PWD = os.path.dirname(os.path.realpath(__file__ ))
CWD = os.getcwd()
from gevent.subprocess import check_output, Popen, PIPE, STDOUT, sleep
import datetime
import json
from dateutil.tz import tzlocal
import sys, signal

from chromedriver import CHROMEDRV_PATH

sys.path.append(CHROMEDRV_PATH)
from mock import patch as mock_patch


def update_auctionPeriod(path):
    with open(path) as file:
        data = json.loads(file.read())
    new_start_time = (datetime.datetime.now(tzlocal()) + datetime.timedelta(seconds=120)).isoformat()
    data["data"]['auctionPeriod']["startDate"] = new_start_time
    with open(path, "w") as file:
        file.write(json.dumps(data, indent=2))

def run_auction(tender_file_path):
    update_auctionPeriod(tender_file_path)
    check_output('{0}/bin/auction_worker planning 11111111111111111111111111111111 {0}/etc/auction_worker_defaults.yaml --auction_info {1}'.format(CWD, tender_file_path).split())
    sleep(30)
    # auction_process = Popen('{0}/bin/auction_worker run 11111111111111111111111111111111 {0}/etc/auction_worker_defaults.json --auction_info {1}'.format(CWD, tender_file_path).split())
    # return auction_process

def main():
    tender_file_path = os.path.join(PWD, "data/tender_data.json")
    auction_process = run_auction(tender_file_path)
    sleep(4)
    # with mock_patch('sys.exit') as exit_mock:
    exit_code = 0
    try:
        run_cli(['-L', 'DEBUG', '--exitonfailure',
                 '-v', 'tender_file_path:{}'.format(tender_file_path),
                 '-v', 'auction_worker_defaults:{0}/etc/auction_worker_defaults.yaml'.format(CWD),
                 '-d', os.path.join(CWD, "logs"), PWD,])
    except SystemExit, e:
        exit_code = e.code
    # try:
    #     os.kill(auction_process.pid, signal.SIGKILL)
    # except OSError, e:
    #     pass
    sys.exit(exit_code)


