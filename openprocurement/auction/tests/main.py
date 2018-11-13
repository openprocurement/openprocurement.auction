from gevent import monkey; monkey.patch_all()

import os
import sys
import argparse
import os.path
import json
import tempfile
import contextlib
from datetime import datetime, timedelta
from dateutil.tz import tzlocal
from robot import run_cli
from pkg_resources import iter_entry_points
from gevent.subprocess import sleep
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities


TESTS = {}
PAUSE_SECONDS = timedelta(seconds=120)
PWD = os.path.dirname(os.path.realpath(__file__))
CWD = os.getcwd()


@contextlib.contextmanager
def update_auctionPeriod(path, auction_type):
    with open(path) as file:
        data = json.loads(file.read())
    new_start_time = (datetime.now(tzlocal()) + PAUSE_SECONDS).isoformat()

    if auction_type == 'simple':
        data['data']['auctionPeriod']['startDate'] = new_start_time
    elif auction_type == 'multilot':
        for lot in data['data']['lots']:
            lot['auctionPeriod']['startDate'] = new_start_time

    with tempfile.NamedTemporaryFile(delete=False) as auction_file:
        json.dump(data, auction_file)
        auction_file.seek(0)
    yield auction_file.name
    auction_file.close()


def main():
    for entry_point in iter_entry_points('openprocurement.auction.robottests'):
        suite = entry_point.load()
        suite(TESTS)

    parser = argparse.ArgumentParser("Auction test runner")
    parser.add_argument('suite',
                        choices=TESTS.keys(),
                        default='simple',
                        help='test_suite')
    parser.add_argument('-f', '--fast-forward',
                        help="run test fast forward",
                        action="store_true")

    parser.add_argument('suite_name',
                        default='auction_test',
                        nargs='?',
                        help='test_suite_name')

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

    if args.suite == 'insider' and args.fast_forward:
        TESTS['insider']['worker_cmd'] += ' --fast-forward'
    test = TESTS.get(args.suite)

    tender_file_path = os.path.join(
        test['suite'], "data/tender_{}.json".format(args.suite))
    auction_id = test['runner'](tender_file_path)

    auction_worker_defaults = test.get('auction_worker_defaults')
    cwd = test.get('cwd')
    cli_args = [
        '-L',
        'DEBUG',
        '--exitonfailure',
        '-v',
        'tender_file_path:{}'.format(tender_file_path),
        '-v', 'auction_id:{}'.format(auction_id),
        '-v', 'BROWSER:{}'.format(args.browser),
        '-v', 'remote_url:{}'.format(remote_url),
        '-v', 'desired_capabilities:{}'.format(desired_capabilities),
        '-v', auction_worker_defaults.format(CWD),
        '-l', '{0}/logs/log_{1}'.format(CWD, args.suite),
        '-r', '{0}/logs/report_{1}'.format(CWD, args.suite),
        '-s', args.suite_name,
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
