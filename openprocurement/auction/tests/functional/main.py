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
from pkg_resources import iter_entry_points


PWD = os.path.dirname(os.path.realpath(__file__))
CWD = os.getcwd()


def run_simple(auction_id):
    with update_auctionPeriod(AUCTION_DATA['simple']['path'], auction_type='simple') as auction_file:
        check_output('{0}/bin/auction_worker planning {1}'
                     ' {0}/etc/auction_worker_defaults.yaml --planning_procerude partial_db --auction_info {2}'.format(CWD, auction_id, auction_file).split())
    sleep(5)


def run_multilot(auction_id, lot_id=''):
    if not lot_id:
        lot_id = "aee0feec3eda4c85bad28eddd78dc3e6"
    with update_auctionPeriod(AUCTION_DATA['multilot']['path'], auction_type='multilot') as auction_file:
        command_line = '{0}/bin/auction_worker planning {1} {0}/etc/auction_worker_defaults.yaml --planning_procerude partial_db --auction_info {2} --lot {3}'.format(
            CWD, auction_id, auction_file, lot_id
        )
        check_output(command_line.split())
    sleep(5)


action_simple = \
    {'data_file': AUCTION_DATA['simple']['path'],
     'runner': run_simple,
     'auction_worker_defaults': 'auction_worker_defaults:{0}/etc/auction_worker_defaults.yaml'.format(CWD)}
action_multilot = \
    {'data_file': AUCTION_DATA['multilot']['path'],
     'runner': run_multilot,
     'auction_worker_defaults': 'auction_worker_defaults:{0}/etc/auction_worker_defaults.yaml'.format(CWD)}


def main():
    tests = {
        'simple': (action_simple,),
        'multilot': (action_multilot,),
        'all': (action_simple, action_multilot)
    }

    for entry_point in iter_entry_points('openprocurement.auction.robottests'):
        suite = entry_point.load()
        suite(tests)

    parser = argparse.ArgumentParser("Auction test runner")
    parser.add_argument('suite', choices=tests.keys(), nargs='?',
                        default='simple', help='test_suite')
    args = parser.parse_args()

    for test in tests.get(args.suite):
        tender_file_path = test['data_file']
        test['runner'](auction_id='11111111111111111111111111111111')
        auction_worker_defaults = test.get('auction_worker_defaults')
        cli_args = ['-L', 'TRACE:INFO', '--exitonfailure',
                    '-v', 'tender_file_path:{}'.format(tender_file_path),
                    '-v', auction_worker_defaults,
                    '-l', '{0}/logs/log_auction'.format(CWD),
                    '-r', '{0}/logs/report_auction'.format(CWD),
                    '-d', os.path.join(CWD, "logs"), PWD]
        try:
            run_cli(cli_args)
        except SystemExit, e:
            exit_code = e.code
    sys.exit(exit_code or 0)
