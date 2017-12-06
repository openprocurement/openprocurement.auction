from gevent import monkey; monkey.patch_all()

import os
import sys
import argparse
import os.path
from robot import run_cli
from pkg_resources import iter_entry_points
from gevent.subprocess import sleep
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities


PWD = os.path.dirname(os.path.realpath(__file__))
CWD = os.getcwd()


def main():
    TESTS = {}
    for entry_point in iter_entry_points('openprocurement.auction.robottests'):
        suite = entry_point.load()
        TESTS.update(suite())

    parser = argparse.ArgumentParser('Auction test runner')
    parser.add_argument('suite',
                        choices=TESTS.keys(),
                        default='simple',
                        nargs='?',
                        help='test_suite')

    parser.add_argument('--browser',
                        dest='browser',
                        choices=['firefox', 'chrome', 'phantomjs'],
                        default='chrome',
                        nargs='?',
                        help='supported browsers')

    parser.add_argument('--ip',
                        dest='ip',
                        nargs='?',
                        help='ip of the remote server where tests will be run')

    parser.add_argument('--port',
                        dest='port',
                        nargs='?',
                        help='port of the remote server where tests will be '
                             'run')

    args = parser.parse_args()

    if args.port and (not args.ip):
        parser.error('The --port argument requires the --ip')

    if args.ip and (args.browser != 'chrome'):
        parser.error('Only chrome is allowed for remote test running')

    port = getattr(args, 'port', '4444')
    remote_url = 'None' if not args.ip else 'http://{}:{}/wd/hub'\
        .format(args.ip, port)

    desired_capabilities = DesiredCapabilities.CHROME if \
        args.browser == 'chrome' else 'None'

    test = TESTS[args.suite]

    test['runner'](test['worker_cmd'], test['tender_file_path'],
                   test['auction_id'])

    auction_worker_defaults = test['auction_worker_defaults']
    cli_args = [
        '-L',
        'TRACE',
        '--exitonfailure',
        '-v', 'tender_file_path:{}'.format(test['tender_file_path']),
        '-v', auction_worker_defaults.format(CWD),
        '-v', 'auction_id:{}'.format(test['auction_id']),
        '-v', 'BROWSER:{}'.format(args.browser),
        '-v', 'remote_url:{}'.format(remote_url),
        '-v', 'desired_capabilities:{}'.format(desired_capabilities),
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
