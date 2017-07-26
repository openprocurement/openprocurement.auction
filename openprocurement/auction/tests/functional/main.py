# -*- coding: utf-8 -*-

from gevent import monkey
monkey.patch_all()

import os.path
import datetime
import json
import sys
import argparse
import contextlib
import tempfile
from dateutil.tz import tzlocal
from pkg_resources import iter_entry_points
from gevent.subprocess import check_output, sleep
from robot import run_cli


PWD = os.path.dirname(os.path.realpath(__file__))
CWD = os.getcwd()


@contextlib.contextmanager
def update_auctionPeriod(path, auction_type):
    with open(path) as file:
        data = json.loads(file.read())
    new_start_time = (datetime.datetime.now(tzlocal()) + datetime.timedelta(seconds=120)).isoformat()
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

def run_simple(tender_file_path, auction_id):
    with update_auctionPeriod(tender_file_path, auction_type='simple') as auction_file:
        check_output('{0}/bin/auction_worker planning {1}'
                     ' {0}/etc/auction_worker_defaults.yaml --planning_procerude partial_db --auction_info {2}'.format(CWD, auction_id, auction_file).split())
    sleep(30)


def run_multilot(tender_file_path, auction_id, lot_id=''):
    if not lot_id:
        lot_id = "aee0feec3eda4c85bad28eddd78dc3e6"
    with update_auctionPeriod(tender_file_path, auction_type='multilot') as auction_file:
        command_line = '{0}/bin/auction_worker planning {1} {0}/etc/auction_worker_defaults.yaml --planning_procerude partial_db --auction_info {2} --lot {3}'.format(
            CWD, auction_id, auction_file, lot_id
        )
        check_output(command_line.split())
    sleep(30)


ACTIONS = {
    'simple': ({'action': run_simple, 'suite_dir': PWD},),
    'multilot': ({'action': run_multilot, 'suite_dir': PWD},),
    'all': ({'action': run_simple, 'suite_dir': PWD},
            {'action': run_multilot, 'suite_dir': PWD})
}


for entry_point in iter_entry_points('openprocurement.auction.robottests'):
    plugin = entry_point.load()
    plugin(ACTIONS)


def main():
    parser = argparse.ArgumentParser("Auction test runner")
    parser.add_argument('suite', choices=ACTIONS.keys(), default='simple', help='test_suite')
    args = parser.parse_args()
    for action in ACTIONS.get(args.suite):
        tender_file_path = os.path.join(action['suite_dir'], "data/tender_{}.json".format(args.suite))
        action['action'](tender_file_path, auction_id="11111111111111111111111111111111")
        auction_worker_defaults = 'auction_worker_defaults:{0}/etc/auction_worker_defaults.yaml'.format(CWD)
        if args.suite == 'dutch':
            auction_worker_defaults = 'auction_worker_defaults:{0}/etc/auction_worker_dutch.yaml'.format(CWD)
        cli_args = ['-L', 'DEBUG', '--exitonfailure',
            '-v', 'tender_file_path:{}'.format(tender_file_path),
            '-v', auction_worker_defaults,
            '-l', '{0}/logs/log_simple_auction'.format(CWD),
            '-r', '{0}/logs/report_simple_auction'.format(CWD),
            '-d', os.path.join(CWD, "logs"), action['suite_dir']
        ]
        sleep(4)
        try:
            run_cli(cli_args)
        except SystemExit, e:
            exit_code = e.code
    sys.exit(exit_code or 0)
