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
import sys


def update_auctionPeriod(path):
    with open(path) as file:
        data = json.loads(file.read())
    new_start_time = (datetime.datetime.now(tzlocal()) + datetime.timedelta(seconds=120)).isoformat()
    if 'lots' in data['data'].keys():
        for lot in data['data']['lots']:
            lot['auctionPeriod']['startDate'] = new_start_time
    else:
        data['data']['auctionPeriod']['startDate'] = new_start_time
    with open(path, "w") as file:
        file.write(json.dumps(data, indent=2))


def run_auction(tender_file_path, auction_id):
    update_auctionPeriod(tender_file_path)

    with open(tender_file_path) as file:
        data = json.loads(file.read())

    lot_id = data['data']['lots'][0]['id'] if 'lots' in data['data'].keys() else None
    lot_cli_append = ' --lot {lot_id}'.format(lot_id=lot_id) if lot_id else ''
    command_line = '{0}/bin/auction_worker planning {1} {0}/etc/auction_worker_defaults.json --planning_procerude partial_db --auction_info {2}' + lot_cli_append
    check_output(command_line.format(CWD, auction_id, tender_file_path).split())
    sleep(30)


def main():
    exit_code = 0

    tender_file_path = os.path.join(PWD, "data/tender_data.json")
    run_auction(tender_file_path, auction_id="11111111111111111111111111111111")
    sleep(4)
    # with mock_patch('sys.exit') as exit_mock:
    try:
        run_cli(['-L', 'DEBUG', '--exitonfailure',
                 '-v', 'tender_file_path:{}'.format(tender_file_path),
                 '-v', 'auction_worker_defaults:{0}/etc/auction_worker_defaults.json'.format(CWD),
                 '-l', '{0}/logs/log_simple_auction'.format(CWD),
                 '-r', '{0}/logs/report_simple_auction'.format(CWD),
                 '-d', os.path.join(CWD, "logs"), PWD,])
    except SystemExit, e:
        exit_code = e.code

    tender_file_path = os.path.join(PWD, "data/tender_multilot_data.json")
    run_auction(tender_file_path, auction_id="22222222222222222222222222222222")
    sleep(4)
    # with mock_patch('sys.exit') as exit_mock:
    try:
        run_cli(['-L', 'DEBUG', '--exitonfailure',
                 '-v', 'tender_file_path:{}'.format(tender_file_path),
                 '-v', 'auction_worker_defaults:{0}/etc/auction_worker_defaults.json'.format(CWD),
                 '-l', '{0}/logs/log_multilot_auction'.format(CWD),
                 '-r', '{0}/logs/report_multilot_auction'.format(CWD),
                 '-d', os.path.join(CWD, "logs"), PWD,])
    except SystemExit, e:
        exit_code = e.code

    sys.exit(exit_code)

