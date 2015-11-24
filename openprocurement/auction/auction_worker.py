# -*- coding: utf-8 -*-
from gevent import monkey, sleep
monkey.patch_all()
##################################
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
from couchdb import Database, Session
from couchdb.http import HTTPError, RETRYABLE_ERRORS
from gevent.event import Event
from gevent.lock import BoundedSemaphore
from gevent.subprocess import call
from apscheduler.schedulers.gevent import GeventScheduler
from requests import Session as RequestsSession
from .server import run_server
from .utils import (
    sorting_by_amount,
    get_latest_bid_for_bidder,
    sorting_start_bids_by_amount,
    patch_tender_data,
    delete_mapping,
    generate_request_id,
    filter_amount
)
from .executor import AuctionsExecutor

from .templates import (
    prepare_initial_bid_stage,
    prepare_bids_stage,
    prepare_service_stage,
    prepare_results_stage,
    get_template
)

from .tenders_types import simple_tender, multiple_lots_tenders

from yaml import safe_dump as yaml_dump
from barbecue import cooking
from fractions import Fraction

from .systemd_msgs_ids import(
    AUCTION_WORKER_DB,
    AUCTION_WORKER_API,
    AUCTION_WORKER_SERVICE,
    AUCTION_WORKER_SYSTEMD_UNITS,
    AUCTION_WORKER_BIDS,
    AUCTION_WORKER_CLEANUP,
    AUCTION_WORKER_SET_AUCTION_URLS
)

MULTILINGUAL_FIELDS = ["title", "description"]
ADDITIONAL_LANGUAGES = ["ru", "en"]

PLANNING_FULL = "full"
PLANNING_PARTIAL_DB = "partial_db"
PLANNING_PARTIAL_CRON = "partial_cron"

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
logger = logging.getLogger('Auction Worker')

SCHEDULER = GeventScheduler(job_defaults={"misfire_grace_time": 100},
                            executors={'default': AuctionsExecutor()},
                            logger=logger)
SCHEDULER.timezone = timezone('Europe/Kiev')


class Auction(object):
    """Auction Worker Class"""
    def __init__(self, tender_id,
                 worker_defaults={},
                 auction_data={},
                 lot_id=None):
        super(Auction, self).__init__()
        self.generate_request_id()
        self.tender_id = tender_id
        self.lot_id = lot_id
        if lot_id:
            self.auction_doc_id = tender_id + "_" + lot_id
        else:
            self.auction_doc_id = tender_id
        self.tender_url = urljoin(
            worker_defaults["TENDERS_API_URL"],
            '/api/{0}/tenders/{1}'.format(
                worker_defaults["TENDERS_API_VERSION"], tender_id
            )
        )
        if auction_data:
            self.debug = True
            logger.setLevel(logging.DEBUG)
            self._auction_data = auction_data
        else:
            self.debug = False
        self.session = RequestsSession()
        self._end_auction_event = Event()
        self.bids_actions = BoundedSemaphore()
        self.worker_defaults = worker_defaults
        self._bids_data = {}
        self.db = Database(str(self.worker_defaults["COUCH_DATABASE"]),
                           session=Session(retry_delays=range(10)))
        self.audit = {}
        self.retries = 10
        self.bidders_count = 0
        self.bidders_data = []
        self.bidders_features = {}
        self.bidders_coeficient = {}
        self.features = None
        self.mapping = {}
        self.rounds_stages = []


    def generate_request_id(self):
        self.request_id = generate_request_id()

    def prepare_public_document(self):
        public_document = deepcopy(dict(self.auction_document))
        not_last_stage = (len(self.auction_document["stages"]) - 1) != self.auction_document["current_stage"]
        if self.features and not_last_stage:
            for stage_name in ['initial_bids', 'stages', 'results']:
                public_document[stage_name] = map(
                    filter_amount,
                    public_document[stage_name]
                )
        return public_document

    def get_auction_document(self, force=False):
        retries = self.retries
        while retries:
            try:
                public_document = self.db.get(self.auction_doc_id)
                if public_document:
                    logger.info("Get auction document {0[_id]} with rev {0[_rev]}".format(public_document),
                                extra={"JOURNAL_REQUEST_ID": self.request_id,
                                       "MESSAGE_ID": AUCTION_WORKER_DB})
                    if not hasattr(self, 'auction_document'):
                        self.auction_document = public_document
                    if force:
                        return public_document
                    elif public_document['_rev'] != self.auction_document['_rev']:
                        logger.warning("Rev error")
                        self.auction_document["_rev"] = public_document["_rev"]
                    logger.debug(json.dumps(self.auction_document, indent=4))
                return public_document

            except HTTPError, e:
                logger.error("Error while get document: {}".format(e),
                             extra={'MESSAGE_ID': AUCTION_WORKER_DB})
            except Exception, e:
                ecode = e.args[0]
                if ecode in RETRYABLE_ERRORS:
                    logger.error("Error while save document: {}".format(e),
                                 extra={'MESSAGE_ID': AUCTION_WORKER_DB})
                else:
                    logger.critical("Unhandled error: {}".format(e),
                                    extra={'MESSAGE_ID': AUCTION_WORKER_DB})
            retries -= 1

    def save_auction_document(self):
        public_document = self.prepare_public_document()
        retries = 10
        while retries:
            try:
                response = self.db.save(public_document)
                if len(response) == 2:
                    logger.info("Saved auction document {0} with rev {1}".format(*response),
                                extra={"JOURNAL_REQUEST_ID": self.request_id,
                                       "MESSAGE_ID": AUCTION_WORKER_DB})
                    self.auction_document['_rev'] = response[1]
                    return response
            except HTTPError, e:
                logger.error("Error while save document: {}".format(e),
                             extra={'MESSAGE_ID': AUCTION_WORKER_DB})
            except Exception, e:
                ecode = e.args[0]
                if ecode in RETRYABLE_ERRORS:
                    logger.error("Error while save document: {}".format(e),
                                 extra={'MESSAGE_ID': AUCTION_WORKER_DB})
                else:
                    logger.critical("Unhandled error: {}".format(e),
                                    extra={'MESSAGE_ID': AUCTION_WORKER_DB})
            if "_rev" in public_document:
                logger.debug("Retry save document changes")
            saved_auction_document = self.get_auction_document(force=True)
            public_document["_rev"] = saved_auction_document["_rev"]
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
            bid_info_result = {key: bid_info[key] for key in BIDS_KEYS_FOR_COPY}
            if self.features:
                bid_info_result['amount_features'] = bid_info['amount_features']
                bid_info_result['coeficient'] = bid_info['coeficient']
            bid_info_result["bidder_name"] = self.mapping[bid_info_result['bidder_id']]
            filtered_bids_data.append(bid_info_result)
        return filtered_bids_data

    def prepare_audit(self):
        self.audit = {
            "id": self.auction_doc_id,
            "tenderId": self._auction_data["data"].get("tenderID", ""),
            "tender_id": self.tender_id,
            "timeline": {
                "auction_start": {
                    "initial_bids": []
                }
            }
        }
        if self.lot_id:
            self.audit["lot_id"] = self.lot_id
        for round_number in range(1, ROUNDS + 1):
            self.audit['timeline']['round_{}'.format(round_number)] = {}

    def approve_audit_info_on_bid_stage(self):
        turn_in_round = self.current_stage - (
            self.current_round * (self.bidders_count + 1) - self.bidders_count
        ) + 1
        round_label = 'round_{}'.format(self.current_round)
        turn_label = 'turn_{}'.format(turn_in_round)
        self.audit['timeline'][round_label][turn_label] = {
            'time': datetime.now(tzlocal()).isoformat(),
            'bidder': self.auction_document["stages"][self.current_stage].get('bidder_id', '')
        }
        if self.auction_document["stages"][self.current_stage].get('changed', False):
            self.audit['timeline'][round_label][turn_label]["bid_time"] = self.auction_document["stages"][self.current_stage]['time']
            self.audit['timeline'][round_label][turn_label]["amount"] = self.auction_document["stages"][self.current_stage]['amount']
            if self.features:
                self.audit['timeline'][round_label][turn_label]["amount_features"] = str(
                    self.auction_document["stages"][self.current_stage].get("amount_features")
                )
                self.audit['timeline'][round_label][turn_label]["coeficient"] = str(
                    self.auction_document["stages"][self.current_stage].get("coeficient")
                )

    def approve_audit_info_on_announcement(self, approved={}):
        self.audit['timeline']['results'] = {
            "time": datetime.now(tzlocal()).isoformat(),
            "bids": []
        }
        for bid in self.auction_document['results']:
            bid_result_audit = {
                'bidder': bid['bidder_id'],
                'amount': bid['amount'],
                'time': bid['time']
            }
            if approved:
                bid_result_audit["identification"] = approved[bid['bidder_id']]
            self.audit['timeline']['results']['bids'].append(bid_result_audit)

    def convert_datetime(self, datetime_stamp):
        return iso8601.parse_date(datetime_stamp).astimezone(SCHEDULER.timezone)

    def get_auction_info(self, prepare=False):
        if self.lot_id:
            multiple_lots_tenders.get_auction_info(self, prepare)
        else:
            simple_tender.get_auction_info(self, prepare)

    def prepare_auction_stages(self):
        # Initital Bids
        for bid_info in self.bidders_data:
            self.auction_document["initial_bids"].append(
                prepare_initial_bid_stage(
                    time="",
                    bidder_id=bid_info["id"],
                    bidder_name=self.mapping[bid_info["id"]],
                    amount="0"
                )
            )
        self.auction_document['stages'] = []
        next_stage_timedelta = self.startDate
        for round_id in xrange(ROUNDS):
            # Schedule PAUSE Stage
            pause_stage = prepare_service_stage(
                start=next_stage_timedelta.isoformat(),
                stage="pause"
            )
            self.auction_document['stages'].append(pause_stage)
            if round_id == 0:
                next_stage_timedelta += timedelta(seconds=FIRST_PAUSE_SECONDS)
            else:
                next_stage_timedelta += timedelta(seconds=PAUSE_SECONDS)

            # Schedule BIDS Stages
            for index in xrange(self.bidders_count):
                bid_stage = prepare_bids_stage({
                    'start': next_stage_timedelta.isoformat(),
                    'bidder_id': '',
                    'bidder_name': '',
                    'amount': '0',
                    'time': ''
                })

                self.auction_document['stages'].append(bid_stage)
                next_stage_timedelta += timedelta(seconds=BIDS_SECONDS)

        self.auction_document['stages'].append(
            prepare_service_stage(
                start=next_stage_timedelta.isoformat(),
                type="pre_announcement"
            )
        )
        self.auction_document['stages'].append(
            prepare_service_stage(
                start="",
                type="announcement"
            )
        )

        self.auction_document['endDate'] = next_stage_timedelta.isoformat()

    ###########################################################################
    #                       Planing methods
    ###########################################################################

    def prepare_auction_document(self):
        self.generate_request_id()
        self.get_auction_info(prepare=True)
        public_document = self.get_auction_document()

        self.auction_document = {}
        if public_document:
            self.auction_document = {"_rev": public_document["_rev"]}
        if self.debug:
            self.auction_document['mode'] = 'test'

        if self.lot_id:
            self.auction_document = multiple_lots_tenders.prepare_auction_document(self)
        else:
            self.auction_document = simple_tender.prepare_auction_document(self)

        self.save_auction_document()
        if not self.debug:
            self.set_auction_and_participation_urls()

    def set_auction_and_participation_urls(self):
        if self.lot_id:
            patch_data = multiple_lots_tenders.prepare_auction_and_participation_urls(self)
        else:
            patch_data = simple_tender.prepare_auction_and_participation_urls(self)

        logger.info("Set auction and participation urls for tender {}".format(
            self.tender_id),
            extra={"JOURNAL_REQUEST_ID": self.request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SET_AUCTION_URLS})
        logger.info(repr(patch_data))
        patch_tender_data(self.tender_url + '/auction', patch_data,
                          user=self.worker_defaults["TENDERS_API_TOKEN"],
                          request_id=self.request_id, session=self.session)

    def prepare_tasks(self, tender_id, start_date):
        cmd = deepcopy(sys.argv)
        cmd[0] = os.path.abspath(cmd[0])
        cmd[1] = 'run'
        home_dir = os.path.expanduser('~')
        with open(os.path.join(home_dir,
                  SYSTEMD_RELATIVE_PATH.format(self.auction_doc_id, 'service')),
                  'w') as service_file:
            template = get_template('systemd.service')
            logger.info(
                "Write configuration to {}".format(service_file.name),
                extra={"JOURNAL_REQUEST_ID": self.request_id,
                       "MESSAGE_ID": AUCTION_WORKER_SYSTEMD_UNITS})
            service_file.write(
                template.render(cmd=' '.join(cmd),
                                description='Auction ' + tender_id,
                                id='auction_' + self.auction_doc_id + '.service'),
            )

        start_time = (start_date - timedelta(minutes=15)).astimezone(tzlocal())
        extra_start_time = datetime.now(tzlocal()) + timedelta(seconds=15)
        if extra_start_time > start_time:
            logger.warning(
                'Planned auction\'s starts date in the past',
                extra={"JOURNAL_REQUEST_ID": self.request_id,
                       "MESSAGE_ID": AUCTION_WORKER_SYSTEMD_UNITS}
            )
            start_time = extra_start_time
            if start_time > start_date:
                logger.error(
                    'We not have a time to start auction',
                    extra={"JOURNAL_REQUEST_ID": self.request_id,
                           "MESSAGE_ID": AUCTION_WORKER_SYSTEMD_UNITS}
                )
                sys.exit()

        with open(os.path.join(home_dir, SYSTEMD_RELATIVE_PATH.format(self.auction_doc_id, 'timer')), 'w') as timer_file:
            template = get_template('systemd.timer')
            logger.info(
                "Write configuration to {}".format(timer_file.name),
                extra={"JOURNAL_REQUEST_ID": self.request_id,
                       "MESSAGE_ID": AUCTION_WORKER_SYSTEMD_UNITS}
            )
            timer_file.write(template.render(
                timestamp=start_time.strftime("%Y-%m-%d %H:%M:%S"),
                description='Auction ' + tender_id)
            )
        logger.info(
            "Reload Systemd",
            extra={"JOURNAL_REQUEST_ID": self.request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SYSTEMD_UNITS}
        )
        response = call(['/usr/bin/systemctl', '--user', 'daemon-reload'])
        logger.info(
            "Systemctl return code: {}".format(response),
            extra={"JOURNAL_REQUEST_ID": self.request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SYSTEMD_UNITS}
        )
        logger.info(
            "Start timer",
            extra={"JOURNAL_REQUEST_ID": self.request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SYSTEMD_UNITS}
        )
        timer_file = 'auction_' + '.'.join([self.auction_doc_id, 'timer'])
        response = call(['/usr/bin/systemctl', '--user',
                         'reload-or-restart', timer_file])
        logger.info(
            "Systemctl 'reload-or-restart' return code: {}".format(response),
            extra={"JOURNAL_REQUEST_ID": self.request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SYSTEMD_UNITS}
        )
        response = call(['/usr/bin/systemctl', '--user',
                         'enable', timer_file])
        logger.info(
            "Systemctl 'enable' return code: {}".format(response),
            extra={"JOURNAL_REQUEST_ID": self.request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SYSTEMD_UNITS}
        )

    def prepare_systemd_units(self):
        self.generate_request_id()
        self.get_auction_document()
        if len(self.auction_document['stages']) >= 1:
            self.prepare_tasks(
                self.auction_document['tenderID'],
                self.convert_datetime(self.auction_document['stages'][0]['start'])
            )
        else:
            logger.error("Not valid auction_document",
                         extra={'MESSAGE_ID': AUCTION_WORKER_SYSTEMD_UNITS})

    ###########################################################################
    #                       Runtime methods
    ###########################################################################

    def schedule_auction(self):
        self.generate_request_id()
        self.get_auction_info()
        self.prepare_audit()
        self.get_auction_document()
        self.prepare_auction_stages()
        self.save_auction_document()
        round_number = 0
        SCHEDULER.add_job(
            self.start_auction, 'date',
            kwargs={"switch_to_round": round_number},
            run_date=self.convert_datetime(
                self.auction_document['stages'][0]['start']
            ),
            name="Start of Auction",
            id="Start of Auction"
        )
        round_number += 1

        SCHEDULER.add_job(
            self.end_first_pause, 'date', kwargs={"switch_to_round": round_number},
            run_date=self.convert_datetime(
                self.auction_document['stages'][1]['start']
            ),
            name="End of Pause Stage: [0 -> 1]",
            id="End of Pause Stage: [0 -> 1]"
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
                    name="End of Bids Stage: [{} -> {}]".format(index - 1, index),
                    id="End of Bids Stage: [{} -> {}]".format(index - 1, index)
                )
            elif self.auction_document['stages'][index - 1]['type'] == 'pause':
                SCHEDULER.add_job(
                    self.next_stage, 'date',
                    kwargs={"switch_to_round": round_number},
                    run_date=self.convert_datetime(
                        self.auction_document['stages'][index]['start']
                    ),
                    name="End of Pause Stage: [{} -> {}]".format(index - 1, index),
                    id="End of Pause Stage: [{} -> {}]".format(index - 1, index)
                )
            round_number += 1
        logger.info(
            "Prepare server ...",
            extra={"JOURNAL_REQUEST_ID": self.request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SERVICE}
        )
        self.server = run_server(self, self.convert_datetime(self.auction_document['stages'][-2]['start']), logger)

    def wait_to_end(self):
        self._end_auction_event.wait()
        logger.info("Stop auction worker",
                    extra={"JOURNAL_REQUEST_ID": self.request_id,
                           "MESSAGE_ID": AUCTION_WORKER_SERVICE})

    def start_auction(self, switch_to_round=None):
        self.generate_request_id()
        self.audit['timeline']['auction_start']['time'] = datetime.now(tzlocal()).isoformat()
        logger.info(
            '---------------- Start auction ----------------',
            extra={"JOURNAL_REQUEST_ID": self.request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SERVICE}
        )
        self.get_auction_info()
        self.get_auction_document()
        # Initital Bids
        bids = deepcopy(self.bidders_data)
        self.auction_document["initial_bids"] = []
        bids_info = sorting_start_bids_by_amount(bids, features=self.features)
        for index, bid in enumerate(bids_info):
            amount = bid["value"]["amount"]
            audit_info = {
                "bidder": bid["id"],
                "date": bid["date"],
                "amount": amount
            }
            if self.features:
                amount_features = cooking(
                    amount,
                    self.features, self.bidders_features[bid["id"]]
                )
                coeficient = self.bidders_coeficient[bid["id"]]
                audit_info["amount_features"] = str(amount_features)
                audit_info["coeficient"] = str(coeficient)
            else:
                coeficient = None
                amount_features = None

            self.audit['timeline']['auction_start']['initial_bids'].append(
                audit_info
            )
            self.auction_document["initial_bids"].append(
                prepare_initial_bid_stage(
                    time=bid["date"] if "date" in bid else self.startDate,
                    bidder_id=bid["id"],
                    bidder_name=self.mapping[bid["id"]],
                    amount=amount,
                    coeficient=coeficient,
                    amount_features=amount_features
                )
            )
        if isinstance(switch_to_round, int):
            self.auction_document["current_stage"] = switch_to_round
        else:
            self.auction_document["current_stage"] = 0

        all_bids = deepcopy(self.auction_document["initial_bids"])
        minimal_bids = []
        for bid_info in self.bidders_data:
            minimal_bids.append(get_latest_bid_for_bidder(
                all_bids, str(bid_info['id'])
            ))

        minimal_bids = self.filter_bids_keys(sorting_by_amount(minimal_bids))
        self.update_future_bidding_orders(minimal_bids)
        self.save_auction_document()

    def end_first_pause(self, switch_to_round=None):
        self.generate_request_id()
        logger.info(
            '---------------- End First Pause ----------------',
            extra={"JOURNAL_REQUEST_ID": self.request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SERVICE}
        )
        self.bids_actions.acquire()
        self.get_auction_document()

        if isinstance(switch_to_round, int):
            self.auction_document["current_stage"] = switch_to_round
        else:
            self.auction_document["current_stage"] += 1

        self.save_auction_document()
        self.bids_actions.release()

    def end_bids_stage(self, switch_to_round=None):
        self.generate_request_id()
        self.bids_actions.acquire()
        self.get_auction_document()
        logger.info(
            '---------------- End Bids Stage ----------------',
            extra={"JOURNAL_REQUEST_ID": self.request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SERVICE}
        )

        self.current_round = self.get_round_number(
            self.auction_document["current_stage"]
        )
        self.current_stage = self.auction_document["current_stage"]

        if self.approve_bids_information():

            start_stage, end_stage = self.get_round_stages(self.current_round)
            all_bids = deepcopy(
                self.auction_document["stages"][start_stage:end_stage]
            )
            minimal_bids = []
            for bid_info in self.bidders_data:
                minimal_bids.append(
                    get_latest_bid_for_bidder(all_bids, bid_info['id'])
                )
            minimal_bids = self.filter_bids_keys(
                sorting_by_amount(minimal_bids)
            )
            self.update_future_bidding_orders(minimal_bids)

        self.approve_audit_info_on_bid_stage()

        if isinstance(switch_to_round, int):
            self.auction_document["current_stage"] = switch_to_round
        else:
            self.auction_document["current_stage"] += 1

        logger.info('---------------- Start stage {0} ----------------'.format(
            self.auction_document["current_stage"]),
            extra={"JOURNAL_REQUEST_ID": self.request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SERVICE}
        )
        self.save_auction_document()
        if self.auction_document["stages"][self.auction_document["current_stage"]]['type'] == 'pre_announcement':
            self.end_auction()
        self.bids_actions.release()
        if self.auction_document["current_stage"] == (len(self.auction_document["stages"]) - 1):
            self._end_auction_event.set()

    def next_stage(self, switch_to_round=None):
        self.generate_request_id()
        self.bids_actions.acquire()
        self.get_auction_document()

        if isinstance(switch_to_round, int):
            self.auction_document["current_stage"] = switch_to_round
        else:
            self.auction_document["current_stage"] += 1
        self.save_auction_document()
        self.bids_actions.release()
        logger.info('---------------- Start stage {0} ----------------'.format(
            self.auction_document["current_stage"]),
            extra={"JOURNAL_REQUEST_ID": self.request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SERVICE}
        )

    def end_auction(self):
        logger.info(
            '---------------- End auction ----------------',
            extra={"JOURNAL_REQUEST_ID": self.request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SERVICE}
        )
        logger.debug("Stop server", extra={"JOURNAL_REQUEST_ID": self.request_id})
        if self.server:
            self.server.stop()
        logger.debug(
            "Clear mapping", extra={"JOURNAL_REQUEST_ID": self.request_id}
        )
        delete_mapping(self.worker_defaults["REDIS_URL"],
                       self.auction_doc_id)

        start_stage, end_stage = self.get_round_stages(ROUNDS)
        minimal_bids = deepcopy(
            self.auction_document["stages"][start_stage:end_stage]
        )
        minimal_bids = self.filter_bids_keys(sorting_by_amount(minimal_bids))
        self.auction_document["results"] = []
        for item in minimal_bids:
            self.auction_document["results"].append(prepare_results_stage(**item))
        self.auction_document["current_stage"] = (len(self.auction_document["stages"]) - 1)
        logger.debug(' '.join((
            'Document in end_stage: \n', yaml_dump(dict(self.auction_document))
        )), extra={"JOURNAL_REQUEST_ID": self.request_id})
        self.approve_audit_info_on_announcement()
        logger.info('Audit data: \n {}'.format(yaml_dump(self.audit)), extra={"JOURNAL_REQUEST_ID": self.request_id})
        if self.debug:
            logger.debug(
                'Debug: put_auction_data disabled !!!',
                extra={"JOURNAL_REQUEST_ID": self.request_id}
            )
            sleep(10)
            self.save_auction_document()
        else:
            if self.put_auction_data():
                self.save_auction_document()
        logger.debug(
            "Fire 'stop auction worker' event",
            extra={"JOURNAL_REQUEST_ID": self.request_id}
        )

    def approve_bids_information(self):
        if self.current_stage in self._bids_data:
            logger.debug(
                "Current stage bids {}".format(self._bids_data[self.current_stage]),
                extra={"JOURNAL_REQUEST_ID": self.request_id}
            )

            bid_info = get_latest_bid_for_bidder(
                self._bids_data[self.current_stage],
                self.auction_document["stages"][self.current_stage]['bidder_id']
            )
            if bid_info['amount'] == -1.0:
                logger.info(
                    "Latest bid is bid cancellation: {}".format(bid_info),
                    extra={"JOURNAL_REQUEST_ID": self.request_id,
                           "MESSAGE_ID": AUCTION_WORKER_BIDS}
                )
                return False
            bid_info = {key: bid_info[key] for key in BIDS_KEYS_FOR_COPY}
            bid_info["bidder_name"] = self.mapping[bid_info['bidder_id']]
            if self.features:
                bid_info['amount_features'] = str(Fraction(bid_info['amount']) / self.bidders_coeficient[bid_info['bidder_id']])
            self.auction_document["stages"][self.current_stage] = prepare_bids_stage(
                self.auction_document["stages"][self.current_stage],
                bid_info
            )
            self.auction_document["stages"][self.current_stage]["changed"] = True

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

                self.auction_document["stages"][stage] = prepare_bids_stage(
                    self.auction_document["stages"][stage],
                    bids[index]
                )

        self.auction_document["results"] = []
        for item in bids:
            self.auction_document["results"].append(prepare_results_stage(**item))

    def put_auction_data(self):
        doc_id = None
        files = {'file': ('audit.yaml', yaml_dump(self.audit, default_flow_style=False))}
        response = patch_tender_data(
            self.tender_url + '/documents', files=files,
            user=self.worker_defaults["TENDERS_API_TOKEN"],
            method='post', request_id=self.request_id, session=self.session,
            retry_count=2
        )
        if response:
            doc_id = response["data"]['id']
            logger.info(
                "Audit log approved. Document id: {}".format(doc_id),
                extra={"JOURNAL_REQUEST_ID": self.request_id,
                       "MESSAGE_ID": AUCTION_WORKER_API}
            )
        else:
            logger.warning(
                "Audit log not approved.",
                extra={"JOURNAL_REQUEST_ID": self.request_id,
                       "MESSAGE_ID": AUCTION_WORKER_API})

        if self.lot_id:
            results = multiple_lots_tenders.post_results_data(self)
        else:
            results = simple_tender.post_results_data(self)

        if results:
            if self.lot_id:
                bids_information = multiple_lots_tenders.announce_results_data(self, results)
            else:
                bids_information = simple_tender.announce_results_data(self, results)

            if doc_id and bids_information:
                self.approve_audit_info_on_announcement(approved=bids_information)
                files = {'file': ('audit.yaml', yaml_dump(self.audit, default_flow_style=False))}
                response = patch_tender_data(
                    self.tender_url + '/documents/{}'.format(doc_id), files=files,
                    user=self.worker_defaults["TENDERS_API_TOKEN"],
                    method='put', request_id=self.request_id,
                    retry_count=2, session=self.session
                )
                if response:
                    doc_id = response["data"]['id']
                    logger.info(
                        "Audit log approved. Document id: {}".format(doc_id),
                        extra={"JOURNAL_REQUEST_ID": self.request_id,
                               "MESSAGE_ID": AUCTION_WORKER_API}
                    )
                else:
                    logger.warning(
                        "Audit log not approved.",
                        extra={"JOURNAL_REQUEST_ID": self.request_id,
                               "MESSAGE_ID": AUCTION_WORKER_API}
                    )

                return True
        else:
            logger.info(
                "Auctions results not approved",
                extra={"JOURNAL_REQUEST_ID": self.request_id,
                       "MESSAGE_ID": AUCTION_WORKER_API}
            )


def cleanup():
    now = datetime.now()
    now = now.replace(now.year, now.month, now.day, 0, 0, 0)
    systemd_files_dir = os.path.join(os.path.expanduser('~'), SYSTEMD_DIRECORY)
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
                            extra={'JOURNAL_TENDER_ID': tender_id,
                                   'MESSAGE_ID': AUCTION_WORKER_CLEANUP}
                        )

                        os.remove(full_filename)
                        full_filename = full_filename[:-5] + 'service'
                        logger.info(
                            'Remove systemd file: {}'.format(full_filename),
                            extra={'JOURNAL_TENDER_ID': tender_id,
                                   'MESSAGE_ID': AUCTION_WORKER_CLEANUP}
                        )
                        os.remove(full_filename)


def main():
    parser = argparse.ArgumentParser(description='---- Auction ----')
    parser.add_argument('cmd', type=str, help='')
    parser.add_argument('auction_doc_id', type=str, help='auction_doc_id')
    parser.add_argument('auction_worker_config', type=str,
                        help='Auction Worker Configuration File')
    parser.add_argument('--auction_info', type=str, help='Auction File')
    parser.add_argument('--with_api_version', type=str, help='Tender Api Version')
    parser.add_argument('--lot', type=str, help='Specify lot in tender', default=None)

    args = parser.parse_args()
    if args.auction_info:
        auction_data = json.load(open(args.auction_info))
    else:
        auction_data = None

    if os.path.isfile(args.auction_worker_config):
        worker_defaults = json.load(open(args.auction_worker_config))
        if args.with_api_version:
            worker_defaults['TENDERS_API_VERSION'] = args.with_api_version
        if args.cmd != 'cleanup':
            worker_defaults['handlers']['journal']['TENDER_ID'] = args.auction_doc_id
            if args.lot:
                worker_defaults['handlers']['journal']['TENDER_LOT_ID'] = args.lot
        for key in ('TENDERS_API_VERSION', 'TENDERS_API_URL',):
            worker_defaults['handlers']['journal'][key] = worker_defaults[key]

        logging.config.dictConfig(worker_defaults)
    else:
        print "Auction worker defaults config not exists!!!"
        sys.exit(1)

    auction = Auction(args.auction_doc_id,
                      worker_defaults=worker_defaults,
                      auction_data=auction_data,
                      lot_id=args.lot)
    if args.cmd == 'run':
        SCHEDULER.start()
        auction.schedule_auction()
        auction.wait_to_end()
        SCHEDULER.shutdown()
    elif args.cmd == 'planning':
        planning_procerude = worker_defaults.get('planning_procerude', PLANNING_FULL)
        if planning_procerude == PLANNING_FULL:
            auction.prepare_auction_document()
            if not auction.debug:
                # auction.prepare_tasks(
                #     auction._auction_data["data"]['tenderID'],
                #     auction.startDate
                # )
                pass
        elif planning_procerude == PLANNING_PARTIAL_DB:
            auction.prepare_auction_document()
        elif planning_procerude == PLANNING_PARTIAL_CRON:
            auction.prepare_systemd_units()
    elif args.cmd == 'cleanup':
        cleanup()


##############################################################
if __name__ == "__main__":
    main()
