# -*- coding: utf-8 -*-

from gevent import monkey
monkey.patch_all()

import os.path
import datetime
import json
import sys
import argparse
from dateutil.tz import tzlocal
from gevent.subprocess import check_output, sleep
from robot import run_cli


PWD = os.path.dirname(os.path.realpath(__file__))
CWD = os.getcwd()


def update_auctionPeriod(path):
    with open(path) as file:
        data = json.loads(file.read())
    new_start_time = (datetime.datetime.now(tzlocal()) + datetime.timedelta(seconds=120)).isoformat()
    if 'lots' in data['data']:
        for lot in data['data']['lots']:
            lot['auctionPeriod']['startDate'] = new_start_time
    data['data']['auctionPeriod']['startDate'] = new_start_time
    with open(path, "w") as file:
        file.write(json.dumps(data, indent=2))


def run_simple(tender_file_path, auction_id):
    update_auctionPeriod(tender_file_path)
    check_output('{0}/bin/auction_worker planning {1}'
                 ' {0}/etc/auction_worker_defaults.yaml --planning_procerude partial_db --auction_info {2}'.format(CWD, auction_id, tender_file_path).split())
    sleep(30)


def run_multilot(tender_file_path, auction_id, lot_id=''):
    if not lot_id:
        lot_id = "aee0feec3eda4c85bad28eddd78dc3e6"
    update_auctionPeriod(tender_file_path)
    command_line = '{0}/bin/auction_worker planning {1} {0}/etc/auction_worker_defaults.yaml --planning_procerude partial_db --auction_info {2} --lot {3}'.format(
        CWD, auction_id, tender_file_path, lot_id
    )
    check_output(command_line.format(CWD, auction_id, tender_file_path).split())
    sleep(30)


def main():
    actions = {
        'simple': (run_simple,),
        'multilot': (run_multilot,),
        'all': (run_simple, run_multilot)
    }

    parser = argparse.ArgumentParser("Auction test runner")
    parser.add_argument('suite', choices=actions.keys(), default='simple', help='test_suite')
    args = parser.parse_args()
    tender_file_path = os.path.join(PWD, "data/tender_{}.json".format(args.suite))
    for action in actions.get(args.suite):
        action(tender_file_path, auction_id="11111111111111111111111111111111")
        sleep(4)
        try:
            run_cli(['-L', 'DEBUG', '--exitonfailure',
                     '-v', 'tender_file_path:{}'.format(tender_file_path),
                     '-v', 'auction_worker_defaults:{0}/etc/auction_worker_defaults.yaml'.format(CWD),
                     '-l', '{0}/logs/log_simple_auction'.format(CWD),
                     '-r', '{0}/logs/report_simple_auction'.format(CWD),
                     '-d', os.path.join(CWD, "logs"), PWD])
        except SystemExit, e:
            exit_code = e.code
    sys.exit(exit_code or 0)
