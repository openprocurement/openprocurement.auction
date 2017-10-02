from gevent import monkey; monkey.patch_all()

import os
import sys
import argparse
import os.path
from robot import run_cli
from pkg_resources import iter_entry_points
from gevent.subprocess import sleep


TESTS = {}
PWD = os.path.dirname(os.path.realpath(__file__))
CWD = os.getcwd()


def main():
    for entry_point in iter_entry_points('openprocurement.auction.robottests'):
        suite = entry_point.load()
        suite(TESTS)

    parser = argparse.ArgumentParser("Auction test runner")
    parser.add_argument('suite',
                        choices=TESTS.keys(),
                        default='simple',
                        help='test_suite')
    args = parser.parse_args()
    test = TESTS.get(args.suite)

    tender_file_path = os.path.join(
        test['suite'], "data/tender_{}.json".format(args.suite))
    test['runner'](tender_file_path)

    auction_worker_defaults = test.get('auction_worker_defaults')
    cli_args = [
        '-L',
        'DEBUG',
        '--exitonfailure',
        '-v',
        'tender_file_path:{}'.format(tender_file_path),
        '-v', auction_worker_defaults.format(CWD),
        '-l', '{0}/logs/log_{1}'.format(CWD, args.suite),
        '-r', '{0}/logs/report_{1}'.format(CWD, args.suite),
        '-P', test['suite'],
        '-d', os.path.join(CWD, "logs"),
        test['suite']
    ]
    sleep(4)
    try:
        run_cli(cli_args)
    except SystemExit, e:
        exit_code = e.code
    sys.exit(exit_code or 0)
