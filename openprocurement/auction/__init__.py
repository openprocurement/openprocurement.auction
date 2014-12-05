# -*- coding: utf-8 -*-
import argparse
import logging
import iso8601
import couchdb
import json
import sys
import os
from dateutil.tz import tzlocal
from copy import deepcopy
from datetime import timedelta, datetime
from pytz import timezone
from gevent.event import Event
from gevent.coros import BoundedSemaphore
from gevent.subprocess import call
from apscheduler.schedulers.gevent import GeventScheduler
from .server import run_server
from .utils import (
    sorting_by_amount,
    get_latest_bid_for_bidder,
    sorting_start_bids_by_amount,
    get_tender_data,
    patch_tender_data
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
TENDER_API_VERSION = '0.4'
TENDER_URL = 'http://api-sandbox.openprocurement.org/api/{0}/tenders/{1}/auction'
SYSTEMD_RELATIVE_PATH = '.config/systemd/user/auction_{0}.{1}'
SCHEDULER = GeventScheduler(job_defaults={"misfire_grace_time": 100})
SCHEDULER.timezone = timezone('Europe/Kiev')

logging.basicConfig(level=logging.INFO,
                    format='%(levelname)s-[%(asctime)s]: %(message)s')


class Auction(object):
    """docstring for Auction"""
    def __init__(self, auction_doc_id, host='', port=8888,
                 database_url='http://localhost:9000/auction',
                 auction_data={}):
        super(Auction, self).__init__()
        self.host = host
        self.port = port
        self.auction_doc_id = auction_doc_id
        self.tender_url = TENDER_URL.format(TENDER_API_VERSION, auction_doc_id)
        if auction_data:
            self.debug = True
            logging.basicConfig(
                level=logging.DEBUG,
                format='%(levelname)s-[%(asctime)s]: %(message)s'
            )
            self._auction_data = auction_data
        self._end_auction_event = Event()
        self.bids_actions = BoundedSemaphore()
        self.database_url = database_url
        self._bids_data = {}
        self.db = couchdb.client.Database(self.database_url)
        self.retries = 10

    def get_auction_document(self):
        retries = self.retries
        while retries:
            try:
                self.auction_document = self.db.get(self.auction_doc_id)
                return
            except couchdb.http.HTTPError, e:
                logging.error("Error while get document: {}".format(e))
            retries -= 1

    def save_auction_document(self):
        retries = 10
        while retries:
            try:
                return self.db.save(self.auction_document)
            except couchdb.http.HTTPError, e:
                logging.error("Error while save document: {}".format(e))
            new_doc = self.auction_document
            if "_rev" in new_doc:
                del new_doc["_rev"]
            self.get_auction_document()
            self.auction_document.update(new_doc)
            logging.debug("Retry save document changes")
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
        if datetime.now(timezone('Europe/Kiev')) > date:
            date = datetime.now(timezone('Europe/Kiev')) + timedelta(seconds=20)
            self._auction_data['data']['auctionPeriod']['startDate'] = date.isoformat()
        return date

    def convert_datetime(self, datetime_stamp):
        return iso8601.parse_date(datetime_stamp).astimezone(SCHEDULER.timezone)

    def get_auction_info(self):
        if not self.debug:
            self._auction_data = get_tender_data(self.tender_url)
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
        self.get_auction_info()
        self.get_auction_document()
        if not self.auction_document:
            self.auction_document = {}
        self.auction_document.update(
            {"_id": self.auction_doc_id, "stages": [],
             "tenderID": self._auction_data["data"].get("tenderID", ""),
             "initial_bids": [], "current_stage": -1, "results": [],
             "minimalStep": self._auction_data["data"]["minimalStep"]}
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

    def prepare_tasks(self):
        cmd = deepcopy(sys.argv)
        cmd[0] = os.path.abspath(cmd[0])
        cmd[1] = 'run'
        home_dir = os.path.expanduser('~')
        logging.info("Get data from {}".format(self.tender_url))
        with open(os.path.join(home_dir,
                  SYSTEMD_RELATIVE_PATH.format(self.auction_doc_id, 'service')),
                  'w') as service_file:
            template = get_template('systemd.service')
            logging.info("Write configuration to {}".format(service_file.name))
            service_file.write(
                template.render(cmd=' '.join(cmd),
                                description='Auction ' + self._auction_data["data"]['tenderID'],
                                id='auction_' + self.auction_doc_id + '.service'),
            )

        start_time = (self.startDate - timedelta(minutes=15)).astimezone(tzlocal())
        with open(os.path.join(home_dir, SYSTEMD_RELATIVE_PATH.format(self.auction_doc_id, 'timer')), 'w') as timer_file:
            template = get_template('systemd.timer')
            logging.info("Write configuration to {}".format(timer_file.name))
            timer_file.write(template.render(
                timestamp=start_time.strftime("%Y-%m-%d %H:%M:%S"),
                description='Auction ' + self._auction_data["data"]['tenderID'])
            )
        logging.info("Reload Systemd")
        response = call(['/usr/bin/systemctl', '--user', 'daemon-reload'])
        logging.info("Systemctl return code: {}".format(response))
        logging.info("Start timer")
        response = call(['/usr/bin/systemctl', '--user',
                         'start', 'auction_' + '.'.join([self.auction_doc_id, 'timer'])])
        logging.info("Systemctl return code: {}".format(response))

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
            )
        )
        round_number += 1

        SCHEDULER.add_job(
            self.end_first_pause, 'date', kwargs={"switch_to_round": round_number},
            run_date=self.convert_datetime(
                self.auction_document['stages'][1]['start']
            )
        )
        round_number += 1

        for index in xrange(2, len(self.auction_document['stages'])):
            if self.auction_document['stages'][index - 1]['type'] == 'bids':
                SCHEDULER.add_job(
                    self.end_bids_stage, 'date',
                    kwargs={"switch_to_round": round_number},
                    run_date=self.convert_datetime(
                        self.auction_document['stages'][index]['start']
                    )
                )
            elif self.auction_document['stages'][index - 1]['type'] == 'pause':
                SCHEDULER.add_job(
                    self.next_stage, 'date',
                    kwargs={"switch_to_round": round_number},
                    run_date=self.convert_datetime(
                        self.auction_document['stages'][index]['start']
                    )
                )
            round_number += 1

        self.server = run_server(self)

    def wait_to_end(self):
        self._end_auction_event.wait()

    def start_auction(self, switch_to_round=None):
        logging.info('---------------- Start auction ----------------')
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
        logging.info('---------------- End First Pause ----------------')
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
        logging.info('---------------- End Bids Stage ----------------')
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
            
        logging.info('---------------- Start stage {0} ----------------'.format(
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
        logging.info('---------------- Start stage {0} ----------------'.format(
            self.auction_document["current_stage"])
        )

    def end_auction(self):
        logging.info('---------------- End auction ----------------')
        self.server.stop()
        start_stage, end_stage = self.get_round_stages(ROUNDS)
        minimal_bids = deepcopy(
            self.auction_document["stages"][start_stage:end_stage]
        )
        minimal_bids = self.filter_bids_keys(sorting_by_amount(minimal_bids))
        self.auction_document["results"] = []
        for item in minimal_bids:
            self.auction_document["results"].append(generate_resuls(item))
        self.auction_document["current_stage"] = (len(self.auction_document["stages"]) - 1)
        logging.info(' '.join((
            'Document in end_stage:', repr(self.auction_document)
        )))
        if self.debug:
            logging.info('Debug: put_auction_data disabled !!!')
        else:
            self.put_auction_data()
        self._end_auction_event.set()

    def approve_bids_information(self):
        current_stage = self.auction_document["current_stage"]
        all_bids = []
        if current_stage in self._bids_data:
            logging.debug(
                "Current stage bids {}".format(self._bids_data[current_stage])
            )
            all_bids += self._bids_data[current_stage]
        if all_bids:
            bid_info = get_latest_bid_for_bidder(
                all_bids,
                self.auction_document["stages"][current_stage]['bidder_id']
            )

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
        logging.info("Approved data: {}".format(all_bids))
        for index, bid_info in enumerate(self._auction_data["data"]["bids"]):
            auction_bid_info = get_latest_bid_for_bidder(all_bids, bid_info["id"])
            self._auction_data["data"]["bids"][index]["value"]["amount"] = auction_bid_info["amount"]
            self._auction_data["data"]["bids"][index]["date"] = auction_bid_info["time"]

        # clear data
        for key in ["status", "minimalStep", "auctionPeriod"]:
            if key in self._auction_data["data"]:
                del self._auction_data["data"][key]

        results = patch_tender_data(self.tender_url, self._auction_data)
        bidders = dict([(bid["id"], bid["tenderers"][0]["name"])
                        for bid in results["data"]["bids"]])
        for section in ['initial_bids', 'stages', 'results']:
            for index, stage in enumerate(self.auction_document[section]):
                if 'bidder_id' in stage and stage['bidder_id'] in bidders:
                    self.auction_document[section][index]["label"]["uk"] = bidders[stage['bidder_id']]
                    self.auction_document[section][index]["label"]["ru"] = bidders[stage['bidder_id']]
                    self.auction_document[section][index]["label"]["en"] = bidders[stage['bidder_id']]


def main():
    parser = argparse.ArgumentParser(description='---- Auction ----')
    parser.add_argument('cmd', type=str, help='')
    parser.add_argument('auction_doc_id', type=str, help='auction_doc_id')
    parser.add_argument('port', type=int, help='Port')
    parser.add_argument('database_url', type=str, help='Database Url')
    parser.add_argument('--auction_info', type=str, help='Auction File')
    args = parser.parse_args()
    if args.auction_info:
        auction_data = json.load(open(args.auction_info))
    else:
        auction_data = None
    auction = Auction(args.auction_doc_id, port=args.port,
                      database_url=args.database_url,
                      auction_data=auction_data)
    if args.cmd == 'run':
        SCHEDULER.start()
        auction.schedule_auction()
        auction.wait_to_end()
        SCHEDULER.shutdown()
    elif args.cmd == 'planning':
        auction.prepare_auction_document()
        auction.prepare_tasks()

##############################################################
if __name__ == "__main__":
    main()
