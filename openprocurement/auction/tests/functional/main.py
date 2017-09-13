# -*- coding: utf-8 -*-

from gevent import monkey
monkey.patch_all()

import os.path
import sys
import argparse
from gevent.subprocess import check_output, sleep
from openprocurement.auction.tests.utils import update_auctionPeriod, \
    AUCTION_DATA
from robot import run_cli


PWD = os.path.dirname(os.path.realpath(__file__))
CWD = os.getcwd()


def run_simple(auction_id):
    with update_auctionPeriod(AUCTION_DATA['simple'], auction_type='simple') as auction_file:
        check_output('{0}/bin/auction_worker planning {1}'
                     ' {0}/etc/auction_worker_defaults.yaml --planning_procerude partial_db --auction_info {2}'.format(CWD, auction_id, auction_file).split())
    sleep(30)


def run_multilot(auction_id, lot_id=''):
    if not lot_id:
        lot_id = "aee0feec3eda4c85bad28eddd78dc3e6"
    with update_auctionPeriod(AUCTION_DATA['multilot'], auction_type='multilot') as auction_file:
        command_line = '{0}/bin/auction_worker planning {1} {0}/etc/auction_worker_defaults.yaml --planning_procerude partial_db --auction_info {2} --lot {3}'.format(
            CWD, auction_id, auction_file, lot_id
        )
        check_output(command_line.split())
    sleep(30)


action_simple = \
    {'data_file': os.path.join(PWD, '..', 'data', 'tender_simple.json'),
     'action': run_simple}
action_multilot = \
    {'data_file': os.path.join(PWD, '..', 'data', 'tender_multilot.json'),
     'action': run_multilot}

ACTIONS = {
    'simple': (action_simple,),
    'multilot': (action_multilot,),
    'all': (action_simple, action_multilot)
}


def main():
    parser = argparse.ArgumentParser("Auction test runner")
    parser.add_argument('suite', choices=ACTIONS.keys(), nargs='?',
                        default='simple', help='test_suite')
    args = parser.parse_args()
    for action in ACTIONS.get(args.suite):
        tender_file_path = action['data_file']
        action['action'](auction_id='11111111111111111111111111111111')
        sleep(4)
        try:
            run_cli(['-L', 'TRACE:INFO', '--exitonfailure',
                     '-v', 'tender_file_path:{}'.format(tender_file_path),
                     '-v', 'auction_worker_defaults:{0}/etc/auction_worker_defaults.yaml'.format(CWD),
                     '-l', '{0}/logs/log_simple_auction'.format(CWD),
                     '-r', '{0}/logs/report_simple_auction'.format(CWD),
                     '-d', os.path.join(CWD, "logs"), PWD])
        except SystemExit, e:
            exit_code = e.code
    sys.exit(exit_code or 0)
