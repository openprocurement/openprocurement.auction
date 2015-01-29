# -*- coding: utf-8 -*-
import argparse
import logging
import logging.config
import iso8601
import json
import sys
import os
import re
from urlparse import urljoin
from dateutil.tz import tzlocal
from copy import deepcopy
from datetime import timedelta, datetime
from pytz import timezone
from couchdb.client import Database
from couchdb.http import HTTPError
from gevent.event import Event
from gevent.coros import BoundedSemaphore
from gevent.subprocess import call
from apscheduler.schedulers.gevent import GeventScheduler
from pkg_resources import parse_version
from .server import run_server
from .utils import (
    sorting_by_amount,
    get_latest_bid_for_bidder,
    sorting_start_bids_by_amount,
    get_tender_data,
    patch_tender_data,
    calculate_hash,
    delete_mapping
)

from .templates import (
    INITIAL_BIDS_TEMPLATE,
    PAUSE_TEMPLATE,
    BIDS_TEMPLATE,
    ANNOUNCEMENT_TEMPLATE,
    generate_resuls,
    generate_bids_stage,
    get_template
)
from gevent import monkey

monkey.patch_all()

ROUNDS = 3
FIRST_PAUSE_SECONDS = 300
PAUSE_SECONDS = 120
BIDS_SECONDS = 120

BIDS_KEYS_FOR_COPY = (
    "bidder_id",
    "amount",
    "time"
)
SYSTEMD_DIRECORY = '.config/systemd/user/'
SYSTEMD_RELATIVE_PATH = SYSTEMD_DIRECORY + 'auction_{0}.{1}'
TIMER_STAMP = re.compile(
    r"OnCalendar=(?P<year>[0-9][0-9][0-9][0-9])"
    r"-(?P<mon>[0-9][0-9])-(?P<day>[0123][0-9]) "
    r"(?P<hour>[0-2][0-9]):(?P<min>[0-5][0-9]):(?P<sec>[0-5][0-9])"
)
SCHEDULER = GeventScheduler(job_defaults={"misfire_grace_time": 100})
SCHEDULER.timezone = timezone('Europe/Kiev')

logger = logging.getLogger('Auction Worker')


class Auction(object):
    """docstring for Auction"""
    def __init__(self, auction_doc_id,
                 worker_defaults={},
                 auction_data={}):
        super(Auction, self).__init__()
        self.auction_doc_id = auction_doc_id
        self.tender_url = urljoin(
            worker_defaults["TENDERS_API_URL"],
            '/api/{0}/tenders/{1}'.format(
                worker_defaults["TENDERS_API_VERSION"], auction_doc_id
            )
        )
        if auction_data:
            self.debug = True
            logger.setLevel(logging.DEBUG)
            self._auction_data = auction_data
        else:
            self.debug = False
        self._end_auction_event = Event()
        self.bids_actions = BoundedSemaphore()
        self.worker_defaults = worker_defaults
        self._bids_data = {}
        self.db = Database(str(self.worker_defaults["COUCH_DATABASE"]))
        self.retries = 10

    def get_auction_document(self):
        retries = self.retries
        while retries:
            try:
                self.auction_document = self.db.get(self.auction_doc_id)
                return
            except HTTPError, e:
                logger.error("Error while get document: {}".format(e))
            retries -= 1

    def save_auction_document(self):
        retries = 10
        while retries:
            try:
                return self.db.save(self.auction_document)
            except HTTPError, e:
                logger.error("Error while save document: {}".format(e))
            new_doc = self.auction_document
            if "_rev" in new_doc:
                del new_doc["_rev"]
            self.get_auction_document()
            self.auction_document.update(new_doc)
            logger.debug("Retry save document changes")
            retries -= 1

    def add_bid(self, round_id, bid):
        if round_id not in self._bids_data:
            self._bids_data[round_id] = []
        self._bids_data[round_id].append(bid)

    def get_round_number(self, stage):
        for index, end_stage in enumerate(self.rounds_stages):
            if stage < end_stage:
                return index
        return ROUNDS

    def get_round_stages(self, round_num):
        return (round_num * (self.bidders_count + 1) - self.bidders_count,
                round_num * (self.bidders_count + 1), )

    def filter_bids_keys(self, bids):
        filtered_bids_data = []
        for bid_info in bids:
            bid_info = {key: bid_info[key] for key in BIDS_KEYS_FOR_COPY}
            bid_info["bidder_name"] = self.mapping[bid_info['bidder_id']]
            filtered_bids_data.append(bid_info)
        return filtered_bids_data

    @property
    def startDate(self):
        date = self.convert_datetime(
            self._auction_data['data']['auctionPeriod']['startDate']
        )
        return date

    def convert_datetime(self, datetime_stamp):
        return iso8601.parse_date(datetime_stamp).astimezone(SCHEDULER.timezone)

    def get_auction_info(self, prepare=False):
        if not self.debug:
            if prepare:
                self._auction_data = get_tender_data(
                    self.tender_url
                )
            else:
                self._auction_data = {'data': {}}
            auction_data = get_tender_data(
                self.tender_url + '/auction',
                user=self.worker_defaults["TENDERS_API_TOKEN"]
            )
            if auction_data:
                self._auction_data['data'].update(auction_data['data'])
                del auction_data
            else:
                self.get_auction_document()
                if self.auction_document:
                    self.auction_document["current_stage"] = -100
                    self.save_auction_document()
                    logger.warning("Cancel auction: {}".format(
                        self.auction_doc_id
                    ))
                else:
                    logger.error("Auction {} not exists".format(
                        self.auction_doc_id
                    ))
                sys.exit(1)

        self.bidders_count = len(self._auction_data["data"]["bids"])
        self.rounds_stages = []
        for stage in range((self.bidders_count + 1) * ROUNDS + 1):
            if (stage + self.bidders_count) % (self.bidders_count + 1) == 0:
                self.rounds_stages.append(stage)
        self.bidders = [bid["id"] for bid in self._auction_data["data"]["bids"]]
        self.mapping = {}
        for index, uid in enumerate(self.bidders):
            self.mapping[uid] = str(index + 1)

    ###########################################################################
    #                       Planing methods
    ###########################################################################

    def prepare_auction_document(self):
        self.get_auction_info(prepare=True)
        self.get_auction_document()
        if not self.auction_document:
            self.auction_document = {}
        # TODO: Get multilingual title and description
        self.auction_document.update(
            {"_id": self.auction_doc_id,
             "stages": [],
             "tenderID": self._auction_data["data"].get("tenderID", ""),
             "title": self._auction_data["data"].get("title", ""),
             "description": self._auction_data["data"].get("description", ""),
             "initial_bids": [],
             "current_stage": -1,
             "results": [],
             "minimalStep": self._auction_data["data"].get("minimalStep", {}),
             "procuringEntity": self._auction_data["data"].get("procuringEntity", {}),
             "items": self._auction_data["data"].get("items", {}),
             "value": self._auction_data["data"].get("value", {})}
        )
        # Initital Bids
        for bid_info in self._auction_data["data"]["bids"]:
            self.auction_document["initial_bids"].append(
                json.loads(INITIAL_BIDS_TEMPLATE.render(
                    time="",
                    bidder_id=bid_info["id"],
                    bidder_name=self.mapping[bid_info["id"]],
                    amount="null"
                ))
            )
        next_stage_timedelta = self.startDate
        for round_id in xrange(ROUNDS):
            # Schedule PAUSE Stage
            pause_stage = json.loads(PAUSE_TEMPLATE.render(
                start=next_stage_timedelta.isoformat()
            ))
            self.auction_document['stages'].append(pause_stage)
            if round_id == 0:
                next_stage_timedelta += timedelta(seconds=FIRST_PAUSE_SECONDS)
            else:
                next_stage_timedelta += timedelta(seconds=PAUSE_SECONDS)

            # Schedule BIDS Stages
            for index in xrange(self.bidders_count):
                bid_stage = json.loads(BIDS_TEMPLATE.render(
                    start=next_stage_timedelta.isoformat(),
                    bidder_id="",
                    bidder_name="",
                    amount="null",
                    time=""
                ))
                self.auction_document['stages'].append(bid_stage)
                next_stage_timedelta += timedelta(seconds=BIDS_SECONDS)

        announcement = json.loads(ANNOUNCEMENT_TEMPLATE.render(
            start=next_stage_timedelta.isoformat()
        ))
        self.auction_document['stages'].append(announcement)
        self.auction_document['endDate'] = next_stage_timedelta.isoformat()
        self.save_auction_document()
        if not self.debug:
            self.set_auction_and_participation_urls()

    def set_auction_and_participation_urls(self):
        if parse_version(self.worker_defaults['TENDERS_API_VERSION']) < parse_version('0.6'):
            logger.info("Version of API not support setup auction url.")
            return None
        auctionUrl = self.worker_defaults["AUCTIONS_URL"].format(
            auction_id=self.auction_doc_id
        )
        logger.info("Set auction and participation urls in {} to {}".format(
            self.tender_url, auctionUrl)
        )
        patch_data = {"data": {"auctionUrl": auctionUrl, "bids": []}}
        for bid in self._auction_data["data"]["bids"]:
            participationUrl = self.worker_defaults["AUCTIONS_URL"].format(
                auction_id=self.auction_doc_id
            )
            participationUrl += '/login?bidder_id={}&hash={}'.format(
                bid["id"],
                calculate_hash(bid["id"], self.worker_defaults["HASH_SECRET"])
            )
            patch_data['data']['bids'].append(
                {"participationUrl": participationUrl,
                 "id": bid["id"]}
            )
        patch_tender_data(self.tender_url + '/auction', patch_data,
                          user=self.worker_defaults["TENDERS_API_TOKEN"])

    def prepare_tasks(self):
        cmd = deepcopy(sys.argv)
        cmd[0] = os.path.abspath(cmd[0])
        cmd[1] = 'run'
        home_dir = os.path.expanduser('~')
        logger.info("Get data from {}".format(self.tender_url))
        with open(os.path.join(home_dir,
                  SYSTEMD_RELATIVE_PATH.format(self.auction_doc_id, 'service')),
                  'w') as service_file:
            template = get_template('systemd.service')
            logger.info("Write configuration to {}".format(service_file.name))
            service_file.write(
                template.render(cmd=' '.join(cmd),
                                description='Auction ' + self._auction_data["data"]['tenderID'],
                                id='auction_' + self.auction_doc_id + '.service'),
            )

        start_time = (self.startDate - timedelta(minutes=15)).astimezone(tzlocal())
        extra_start_time = datetime.now(tzlocal()) + timedelta(seconds=15)
        if extra_start_time > start_time:
            logger.warning('Planned auction\'s starts date in the past')
            start_time = extra_start_time
            if start_time > self.startDate:
                logger.error('We not have a time to start auction')
                sys.exit()

        with open(os.path.join(home_dir, SYSTEMD_RELATIVE_PATH.format(self.auction_doc_id, 'timer')), 'w') as timer_file:
            template = get_template('systemd.timer')
            logger.info("Write configuration to {}".format(timer_file.name))
            timer_file.write(template.render(
                timestamp=start_time.strftime("%Y-%m-%d %H:%M:%S"),
                description='Auction ' + self._auction_data["data"]['tenderID'])
            )
        logger.info("Reload Systemd")
        response = call(['/usr/bin/systemctl', '--user', 'daemon-reload'])
        logger.info("Systemctl return code: {}".format(response))
        logger.info("Start timer")
        response = call(['/usr/bin/systemctl', '--user',
                         'reload-or-restart', 'auction_' + '.'.join([self.auction_doc_id, 'timer'])])
        logger.info("Systemctl return code: {}".format(response))

    ###########################################################################
    #                       Runtime methods
    ###########################################################################

    def schedule_auction(self):
        self.get_auction_info()
        self.get_auction_document()
        round_number = 0
        SCHEDULER.add_job(
            self.start_auction, 'date',
            kwargs={"switch_to_round": round_number},
            run_date=self.convert_datetime(
                self.auction_document['stages'][0]['start']
            ),
            name="Start of Auction"
        )
        round_number += 1

        SCHEDULER.add_job(
            self.end_first_pause, 'date', kwargs={"switch_to_round": round_number},
            run_date=self.convert_datetime(
                self.auction_document['stages'][1]['start']
            ),
            name="End of Pause Stage: [0 -> 1]"

        )
        round_number += 1

        for index in xrange(2, len(self.auction_document['stages'])):
            if self.auction_document['stages'][index - 1]['type'] == 'bids':
                SCHEDULER.add_job(
                    self.end_bids_stage, 'date',
                    kwargs={"switch_to_round": round_number},
                    run_date=self.convert_datetime(
                        self.auction_document['stages'][index]['start']
                    ),
                    name="End of Bids Stage: [{} -> {}]".format(index - 1, index)
                )
            elif self.auction_document['stages'][index - 1]['type'] == 'pause':
                SCHEDULER.add_job(
                    self.next_stage, 'date',
                    kwargs={"switch_to_round": round_number},
                    run_date=self.convert_datetime(
                        self.auction_document['stages'][index]['start']
                    ),
                    name="End of Pause Stage: [{} -> {}]".format(index - 1, index)
                )
            round_number += 1
        logger.info("Prepare server ...")
        self.server = run_server(self, self.convert_datetime(
            self.auction_document['stages'][index]['start']
        ), logger)

    def wait_to_end(self):
        self._end_auction_event.wait()

    def start_auction(self, switch_to_round=None):
        logger.info('---------------- Start auction ----------------')
        self.get_auction_info()
        self.get_auction_document()
        # Initital Bids
        bids = deepcopy(self._auction_data['data']['bids'])
        self.auction_document["initial_bids"] = []
        bids_info = sorting_start_bids_by_amount(bids)
        for index, bid in enumerate(bids_info):
            self.auction_document["initial_bids"].append(
                json.loads(INITIAL_BIDS_TEMPLATE.render(
                    time=bid["date"] if "date" in bid else self.startDate,
                    bidder_id=bid["id"],
                    bidder_name=self.mapping[bid["id"]],
                    amount=bid["value"]["amount"]
                ))
            )

        if isinstance(switch_to_round, int):
            self.auction_document["current_stage"] = switch_to_round
        else:
            self.auction_document["current_stage"] = 0

        all_bids = deepcopy(self.auction_document["initial_bids"])
        minimal_bids = []
        for bidder in self.bidders:
            minimal_bids.append(get_latest_bid_for_bidder(
                all_bids, str(bidder)
            ))
        minimal_bids = self.filter_bids_keys(sorting_by_amount(minimal_bids))
        self.update_future_bidding_orders(minimal_bids)
        self.save_auction_document()

    def end_first_pause(self, switch_to_round=None):
        logger.info('---------------- End First Pause ----------------')
        self.bids_actions.acquire()
        self.get_auction_document()

        if isinstance(switch_to_round, int):
            self.auction_document["current_stage"] = switch_to_round
        else:
            self.auction_document["current_stage"] += 1

        self.save_auction_document()
        self.bids_actions.release()

    def end_bids_stage(self, switch_to_round=None):
        self.bids_actions.acquire()
        self.get_auction_document()
        logger.info('---------------- End Bids Stage ----------------')
        if self.approve_bids_information():
            current_round = self.get_round_number(
                self.auction_document["current_stage"]
            )
            start_stage, end_stage = self.get_round_stages(current_round)
            all_bids = deepcopy(
                self.auction_document["stages"][start_stage:end_stage]
            )
            minimal_bids = []
            for bidder_id in self.bidders:
                minimal_bids.append(
                    get_latest_bid_for_bidder(all_bids, bidder_id)
                )
            minimal_bids = self.filter_bids_keys(
                sorting_by_amount(minimal_bids)
            )
            self.update_future_bidding_orders(minimal_bids)

        if isinstance(switch_to_round, int):
            self.auction_document["current_stage"] = switch_to_round
        else:
            self.auction_document["current_stage"] += 1
            
        logger.info('---------------- Start stage {0} ----------------'.format(
            self.auction_document["current_stage"])
        )
        if self.auction_document["current_stage"] == (len(self.auction_document["stages"]) - 1):
            self.end_auction()
        self.save_auction_document()
        self.bids_actions.release()

    def next_stage(self, switch_to_round=None):
        self.bids_actions.acquire()
        self.get_auction_document()

        if isinstance(switch_to_round, int):
            self.auction_document["current_stage"] = switch_to_round
        else:
            self.auction_document["current_stage"] += 1
        self.save_auction_document()
        self.bids_actions.release()
        logger.info('---------------- Start stage {0} ----------------'.format(
            self.auction_document["current_stage"])
        )

    def end_auction(self):
        logger.info('---------------- End auction ----------------')
        start_stage, end_stage = self.get_round_stages(ROUNDS)
        minimal_bids = deepcopy(
            self.auction_document["stages"][start_stage:end_stage]
        )
        minimal_bids = self.filter_bids_keys(sorting_by_amount(minimal_bids))
        self.auction_document["results"] = []
        for item in minimal_bids:
            self.auction_document["results"].append(generate_resuls(item))
        self.auction_document["current_stage"] = (len(self.auction_document["stages"]) - 1)
        logger.info(' '.join((
            'Document in end_stage:', repr(self.auction_document)
        )))
        if self.debug:
            logger.info('Debug: put_auction_data disabled !!!')
        else:
            self.put_auction_data()
        logger.info("Clear mapping")
        delete_mapping(self.worker_defaults["REDIS_URL"],
                       self.auction_doc_id)
        logger.info("Stop server")
        if self.server:
            self.server.stop()
        logger.info("Fire 'stop auction worker' event")
        self._end_auction_event.set()

    def approve_bids_information(self):
        current_stage = self.auction_document["current_stage"]

        if current_stage in self._bids_data:
            logger.debug(
                "Current stage bids {}".format(self._bids_data[current_stage])
            )

            bid_info = get_latest_bid_for_bidder(
                self._bids_data[current_stage],
                self.auction_document["stages"][current_stage]['bidder_id']
            )
            if bid_info['amount'] == -1:
                logger.info(
                    "Latest bid is bid cancellation: {}".format(bid_info)
                )
                return False
            bid_info = {key: bid_info[key] for key in BIDS_KEYS_FOR_COPY}
            bid_info["bidder_name"] = self.mapping[bid_info['bidder_id']]
            self.auction_document["stages"][current_stage] = generate_bids_stage(
                self.auction_document["stages"][current_stage],
                bid_info
            )
            self.auction_document["stages"][current_stage]["changed"] = True
            return True
        else:
            return False

    def update_future_bidding_orders(self, bids):
        current_round = self.get_round_number(
            self.auction_document["current_stage"]
        )
        for round_number in range(current_round + 1, ROUNDS + 1):
            for index, stage in enumerate(
                    range(*self.get_round_stages(round_number))):

                self.auction_document["stages"][stage] = generate_bids_stage(
                    self.auction_document["stages"][stage],
                    bids[index]
                )

        self.auction_document["results"] = []
        for item in bids:
            self.auction_document["results"].append(generate_resuls(item))

    def put_auction_data(self):
        all_bids = self.auction_document["results"]
        logger.info("Approved data: {}".format(all_bids))
        for index, bid_info in enumerate(self._auction_data["data"]["bids"]):
            auction_bid_info = get_latest_bid_for_bidder(all_bids, bid_info["id"])
            self._auction_data["data"]["bids"][index]["value"]["amount"] = auction_bid_info["amount"]
            self._auction_data["data"]["bids"][index]["date"] = auction_bid_info["time"]

        # clear data
        data = {'data': {'bids': self._auction_data["data"]['bids']}}

        if parse_version(self.worker_defaults['TENDERS_API_VERSION']) < parse_version('0.6'):
            results_submit_method = 'patch'
        else:
            results_submit_method = 'post'
        results = patch_tender_data(
            self.tender_url + '/auction', data,
            user=self.worker_defaults["TENDERS_API_TOKEN"],
            method=results_submit_method
        )
        if results:
            bidders = dict([(bid["id"], bid["tenderers"][0]["name"])
                            for bid in results["data"]["bids"]])
            for section in ['initial_bids', 'stages', 'results']:
                for index, stage in enumerate(self.auction_document[section]):
                    if 'bidder_id' in stage and stage['bidder_id'] in bidders:
                        self.auction_document[section][index]["label"]["uk"] = bidders[stage['bidder_id']]
                        self.auction_document[section][index]["label"]["ru"] = bidders[stage['bidder_id']]
                        self.auction_document[section][index]["label"]["en"] = bidders[stage['bidder_id']]


def cleanup():
    now = datetime.now()
    now = now.replace(now.year, now.month, now.day, 0, 0, 0)
    systemd_files_dir =  os.path.join(os.path.expanduser('~'), SYSTEMD_DIRECORY)
    for (dirpath, dirnames, filenames) in os.walk(systemd_files_dir):
        for filename in filenames:
            if filename.startswith('auction_') and filename.endswith('.timer'):
                tender_id = filename[8:-6]
                full_filename = os.path.join(systemd_files_dir, filename)
                with open(full_filename) as timer_file:
                    r = TIMER_STAMP.search(timer_file.read())
                if r:
                    datetime_args = [int(term) for term in r.groups()]
                    if datetime(*datetime_args) < now:
                        logger.info(
                            'Remove systemd file: {}'.format(full_filename),
                            extra={'JOURNAL_TENDER_ID': tender_id}
                        )

                        os.remove(full_filename)
                        full_filename = full_filename[:-5] + 'service'
                        logger.info(
                            'Remove systemd file: {}'.format(full_filename),
                            extra={'JOURNAL_TENDER_ID': tender_id}
                        )
                        os.remove(full_filename)

def main():
    parser = argparse.ArgumentParser(description='---- Auction ----')
    parser.add_argument('cmd', type=str, help='')
    parser.add_argument('auction_doc_id', type=str, help='auction_doc_id')
    parser.add_argument('auction_worker_config', type=str,
                        help='Auction Worker Configuration File')
    parser.add_argument('--auction_info', type=str, help='Auction File')
    args = parser.parse_args()
    if args.auction_info:
        auction_data = json.load(open(args.auction_info))
    else:
        auction_data = None

    if os.path.isfile(args.auction_worker_config):
        worker_defaults = json.load(open(args.auction_worker_config))
        if args.cmd != 'cleanup':
            worker_defaults['handlers']['journal']['TENDER_ID'] = args.auction_doc_id
        for key in ('TENDERS_API_VERSION', 'TENDERS_API_URL',):
            worker_defaults['handlers']['journal'][key] = worker_defaults[key]

        logging.config.dictConfig(worker_defaults)
    else:
        print "Auction worker defaults config not exists!!!"
        sys.exit(1)

    auction = Auction(args.auction_doc_id,
                      worker_defaults=worker_defaults,
                      auction_data=auction_data)
    if args.cmd == 'run':
        SCHEDULER.start()
        auction.schedule_auction()
        auction.wait_to_end()
        SCHEDULER.shutdown()
    elif args.cmd == 'planning':
        auction.prepare_auction_document()
        auction.prepare_tasks()
    elif args.cmd == 'cleanup':
        cleanup()


##############################################################
if __name__ == "__main__":
    main()
