import logging
import json
import iso8601
from gevent import sleep
from datetime import datetime, timedelta
from copy import deepcopy
from pytz import timezone
from dateutil.tz import tzlocal
from yaml import safe_dump as yaml_dump
from couchdb.http import HTTPError, RETRYABLE_ERRORS
from fractions import Fraction
from barbecue import cooking
from apscheduler.schedulers.gevent import GeventScheduler

from openprocurement.auction.executor import AuctionsExecutor
from openprocurement.auction.server import run_server
from openprocurement.auction.systemd_msgs_ids import (
    AUCTION_WORKER_DB_GET_DOC,
    AUCTION_WORKER_DB_GET_DOC_ERROR,
    AUCTION_WORKER_DB_GET_DOC_UNHANDLED_ERROR,
    AUCTION_WORKER_DB_SAVE_DOC,
    AUCTION_WORKER_DB_SAVE_DOC_ERROR,
    AUCTION_WORKER_DB_SAVE_DOC_UNHANDLED_ERROR,
    AUCTION_WORKER_API_AUDIT_LOG_APPROVED,
    AUCTION_WORKER_API_AUDIT_LOG_NOT_APPROVED,
    AUCTION_WORKER_BIDS_LATEST_BID_CANCELLATION,
    AUCTION_WORKER_API_AUCTION_RESULT_NOT_APPROVED,
    AUCTION_WORKER_SERVICE_END_BID_STAGE,
    AUCTION_WORKER_SERVICE_START_STAGE,
    AUCTION_WORKER_SERVICE_START_NEXT_STAGE,
    AUCTION_WORKER_SERVICE_AUCTION_RESCHEDULE,
    AUCTION_WORKER_SERVICE_AUCTION_NOT_FOUND,
    AUCTION_WORKER_SERVICE_AUCTION_STATUS_CANCELED,
    AUCTION_WORKER_SERVICE_AUCTION_CANCELED,
    AUCTION_WORKER_SERVICE_END_AUCTION,
    AUCTION_WORKER_SERVICE_START_AUCTION,
    AUCTION_WORKER_SERVICE_STOP_AUCTION_WORKER,
    AUCTION_WORKER_SERVICE_PREPARE_SERVER,
    AUCTION_WORKER_SERVICE_END_FIRST_PAUSE
)
from openprocurement.auction.utils import\
    filter_amount, generate_request_id, make_request,\
    get_latest_bid_for_bidder, sorting_by_amount,\
    sorting_start_bids_by_amount, delete_mapping
from openprocurement.auction.tenders_types import\
    simple_tender
from openprocurement.auction.templates import prepare_bids_stage,\
    prepare_service_stage, prepare_initial_bid_stage, prepare_results_stage


ROUNDS = 3
LOGGER = logging.getLogger("Auction Worker")
TIMEZONE = timezone('Europe/Kiev')
BIDS_SECONDS = 120
FIRST_PAUSE_SECONDS = 300
PAUSE_SECONDS = 120
BIDS_KEYS_FOR_COPY = ("bidder_id", "amount", "time")


SCHEDULER = GeventScheduler(job_defaults={"misfire_grace_time": 100},
                            executors={'default': AuctionsExecutor()},
                            logger=LOGGER)
SCHEDULER.timezone = TIMEZONE 


class DBServiceMixin(object):
    """ Mixin class to work with couchdb"""

    def get_auction_info(self, prepare=False):
        simple_tender.get_auction_info(self, prepare)

    def prepare_public_document(self):
        public_document = deepcopy(dict(self.auction_document))
        not_last_stage = self.auction_document["current_stage"] not in (len(self.auction_document["stages"]) - 1,
                                                                        len(self.auction_document["stages"]) - 2,)
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
                    LOGGER.info("Get auction document {0[_id]} with rev {0[_rev]}".format(public_document),
                                extra={"JOURNAL_REQUEST_ID": self.request_id,
                                       "MESSAGE_ID": AUCTION_WORKER_DB_GET_DOC})
                    if not hasattr(self, 'auction_document'):
                        self.auction_document = public_document
                    if force:
                        return public_document
                    elif public_document['_rev'] != self.auction_document['_rev']:
                        LOGGER.warning("Rev error")
                        self.auction_document["_rev"] = public_document["_rev"]
                    LOGGER.debug(json.dumps(self.auction_document, indent=4))
                return public_document

            except HTTPError, e:
                LOGGER.error("Error while get document: {}".format(e),
                             extra={'MESSAGE_ID': AUCTION_WORKER_DB_GET_DOC_ERROR})
            except Exception, e:
                ecode = e.args[0]
                if ecode in RETRYABLE_ERRORS:
                    LOGGER.error("Error while get document: {}".format(e),
                                 extra={'MESSAGE_ID': AUCTION_WORKER_DB_GET_DOC_ERROR})
                else:
                    LOGGER.critical("Unhandled error: {}".format(e),
                                    extra={'MESSAGE_ID': AUCTION_WORKER_DB_GET_DOC_UNHANDLED_ERROR})
            retries -= 1

    def save_auction_document(self):
        public_document = self.prepare_public_document()
        retries = 10
        while retries:
            try:
                response = self.db.save(public_document)
                if len(response) == 2:
                    LOGGER.info("Saved auction document {0} with rev {1}".format(*response),
                                extra={"JOURNAL_REQUEST_ID": self.request_id,
                                       "MESSAGE_ID": AUCTION_WORKER_DB_SAVE_DOC})
                    self.auction_document['_rev'] = response[1]
                    return response
            except HTTPError, e:
                LOGGER.error("Error while save document: {}".format(e),
                             extra={'MESSAGE_ID': AUCTION_WORKER_DB_SAVE_DOC_ERROR})
            except Exception, e:
                ecode = e.args[0]
                if ecode in RETRYABLE_ERRORS:
                    LOGGER.error("Error while save document: {}".format(e),
                                 extra={'MESSAGE_ID': AUCTION_WORKER_DB_SAVE_DOC_ERROR})
                else:
                    LOGGER.critical("Unhandled error: {}".format(e),
                                    extra={'MESSAGE_ID': AUCTION_WORKER_DB_SAVE_DOC_UNHANDLED_ERROR})
            if "_rev" in public_document:
                LOGGER.debug("Retry save document changes")
            saved_auction_document = self.get_auction_document(force=True)
            public_document["_rev"] = saved_auction_document["_rev"]
            retries -= 1

    def prepare_auction_document(self):
        self.generate_request_id()
        public_document = self.get_auction_document()

        self.auction_document = {}
        if public_document:
            self.auction_document = {"_rev": public_document["_rev"]}
        if self.debug:
            self.auction_document['mode'] = 'test'
            self.auction_document['test_auction_data'] = deepcopy(self._auction_data)

        self.get_auction_info(prepare=True)
        if self.worker_defaults.get('sandbox_mode', False):
            submissionMethodDetails = self._auction_data['data'].get('submissionMethodDetails', '')
            if submissionMethodDetails == 'quick(mode:no-auction)':
                results = simple_tender.post_results_data(self, with_auctions_results=False)
                return 0
            elif submissionMethodDetails == 'quick(mode:fast-forward)':
                self.auction_document = simple_tender.prepare_auction_document(self)
                if not self.debug:
                    self.set_auction_and_participation_urls()
                self.get_auction_info()
                self.prepare_auction_stages_fast_forward()
                self.save_auction_document()
                simple_tender.post_results_data(self, with_auctions_results=False)
                simple_tender.announce_results_data(self, None)
                self.save_auction_document()
                return

        self.auction_document = simple_tender.prepare_auction_document(self)

        self.save_auction_document()
        if not self.debug:
            self.set_auction_and_participation_urls()


class RequestIDServiceMixin(object):
    """ Simpel mixin class """
    def generate_request_id(self):
        self.request_id = generate_request_id()


class AuditServiceMixin(object):
    """ Mixin class to create, modify and upload audit documents"""
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

    def upload_audit_file_with_document_service(self, doc_id=None):
        files = {'file': ('audit_{}.yaml'.format(self.auction_doc_id),
                          yaml_dump(self.audit, default_flow_style=False))}
        ds_response = make_request(self.worker_defaults["DOCUMENT_SERVICE"]["url"],
                                   files=files, method='post',
                                   user=self.worker_defaults["DOCUMENT_SERVICE"]["username"],
                                   password=self.worker_defaults["DOCUMENT_SERVICE"]["password"],
                                   session=self.session_ds, retry_count=3)

        if doc_id:
            method = 'put'
            path = self.tender_url + '/documents/{}'.format(doc_id)
        else:
            method = 'post'
            path = self.tender_url + '/documents'

        response = make_request(path, data=ds_response,
                                user=self.worker_defaults["TENDERS_API_TOKEN"],
                                method=method, request_id=self.request_id, session=self.session,
                                retry_count=2
                                )
        if response:
            doc_id = response["data"]['id']
            LOGGER.info(
                "Audit log approved. Document id: {}".format(doc_id),
                extra={"JOURNAL_REQUEST_ID": self.request_id,
                       "MESSAGE_ID": AUCTION_WORKER_API_AUDIT_LOG_APPROVED}
            )
            return doc_id
        else:
            LOGGER.warning(
                "Audit log not approved.",
                extra={"JOURNAL_REQUEST_ID": self.request_id,
                       "MESSAGE_ID": AUCTION_WORKER_API_AUDIT_LOG_NOT_APPROVED})

    def upload_audit_file_without_document_service(self, doc_id=None):
        files = {'file': ('audit_{}.yaml'.format(self.auction_doc_id),
                          yaml_dump(self.audit, default_flow_style=False))}
        if doc_id:
            method = 'put'
            path = self.tender_url + '/documents/{}'.format(doc_id)
        else:
            method = 'post'
            path = self.tender_url + '/documents'

        response = make_request(path, files=files,
                                user=self.worker_defaults["TENDERS_API_TOKEN"],
                                method=method, request_id=self.request_id, session=self.session,
                                retry_count=2
                                )
        if response:
            doc_id = response["data"]['id']
            LOGGER.info(
                "Audit log approved. Document id: {}".format(doc_id),
                extra={"JOURNAL_REQUEST_ID": self.request_id,
                       "MESSAGE_ID": AUCTION_WORKER_API_AUDIT_LOG_APPROVED}
            )
            return doc_id
        else:
            LOGGER.warning(
                "Audit log not approved.",
                extra={"JOURNAL_REQUEST_ID": self.request_id,
                       "MESSAGE_ID": AUCTION_WORKER_API_AUDIT_LOG_NOT_APPROVED})


class DateTimeServiceMixin(object):
    """ Simple time convertion mixin"""
    def convert_datetime(self, datetime_stamp):
        return iso8601.parse_date(datetime_stamp).astimezone(TIMEZONE)


class BiddersServiceMixin(object):
    """Mixin class to work with bids data"""

    def add_bid(self, round_id, bid):
        if round_id not in self._bids_data:
            self._bids_data[round_id] = []
        self._bids_data[round_id].append(bid)

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

    def set_auction_and_participation_urls(self):
        simple_tender.prepare_auction_and_participation_urls(self)

    def approve_bids_information(self):
        if self.current_stage in self._bids_data:
            LOGGER.info(
                "Current stage bids {}".format(self._bids_data[self.current_stage]),
                extra={"JOURNAL_REQUEST_ID": self.request_id}
            )

            bid_info = get_latest_bid_for_bidder(
                self._bids_data[self.current_stage],
                self.auction_document["stages"][self.current_stage]['bidder_id']
            )
            if bid_info['amount'] == -1.0:
                LOGGER.info(
                    "Latest bid is bid cancellation: {}".format(bid_info),
                    extra={"JOURNAL_REQUEST_ID": self.request_id,
                           "MESSAGE_ID": AUCTION_WORKER_BIDS_LATEST_BID_CANCELLATION}
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


class PostAuctionServiceMixin(object):

    def put_auction_data(self):
        if self.worker_defaults.get('with_document_service', False):
            doc_id = self.upload_audit_file_with_document_service()
        else:
            doc_id = self.upload_audit_file_without_document_service()
        results = simple_tender.post_results_data(self)
        if results:
            bids_information = simple_tender.announce_results_data(self, results)
            if doc_id and bids_information:
                self.approve_audit_info_on_announcement(approved=bids_information)
                if self.worker_defaults.get('with_document_service', False):
                    doc_id = self.upload_audit_file_with_document_service(doc_id)
                else:
                    doc_id = self.upload_audit_file_without_document_service(doc_id)

                return True
        else:
            LOGGER.info(
                "Auctions results not approved",
                extra={"JOURNAL_REQUEST_ID": self.request_id,
                       "MESSAGE_ID": AUCTION_WORKER_API_AUCTION_RESULT_NOT_APPROVED}
            )

    def post_announce(self):
        self.generate_request_id()
        self.get_auction_document()
        simple_tender.announce_results_data(self, None)
        self.save_auction_document()


class StagesServiceMixin(object):

    def get_round_number(self, stage):
        for index, end_stage in enumerate(self.rounds_stages):
            if stage < end_stage:
                return index
        return ROUNDS

    def get_round_stages(self, round_num):
        return (round_num * (self.bidders_count + 1) - self.bidders_count,
                round_num * (self.bidders_count + 1), )
 
    def prepare_auction_stages_fast_forward(self):
        self.auction_document['auction_type'] = 'meat' if self.features else 'default'
        bids = deepcopy(self.bidders_data)
        self.auction_document["initial_bids"] = []
        bids_info = sorting_start_bids_by_amount(bids, features=self.features)
        for index, bid in enumerate(bids_info):
            amount = bid["value"]["amount"]
            if self.features:
                amount_features = cooking(
                    amount,
                    self.features, self.bidders_features[bid["id"]]
                )
                coeficient = self.bidders_coeficient[bid["id"]]

            else:
                coeficient = None
                amount_features = None
            initial_bid_stage = prepare_initial_bid_stage(
                time=bid["date"] if "date" in bid else self.startDate,
                bidder_id=bid["id"],
                bidder_name=self.mapping[bid["id"]],
                amount=amount,
                coeficient=coeficient,
                amount_features=amount_features
            )
            self.auction_document["initial_bids"].append(
                initial_bid_stage
            )
        self.auction_document['stages'] = []
        next_stage_timedelta = datetime.now(tzlocal())
        for round_id in xrange(ROUNDS):
            # Schedule PAUSE Stage
            pause_stage = prepare_service_stage(
                start=next_stage_timedelta.isoformat(),
                stage="pause"
            )
            self.auction_document['stages'].append(pause_stage)
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
        all_bids = deepcopy(self.auction_document["initial_bids"])
        minimal_bids = []
        for bid_info in self.bidders_data:
            minimal_bids.append(get_latest_bid_for_bidder(
                all_bids, str(bid_info['id'])
            ))

        minimal_bids = self.filter_bids_keys(sorting_by_amount(minimal_bids))
        self.update_future_bidding_orders(minimal_bids)

        self.auction_document['endDate'] = next_stage_timedelta.isoformat()
        self.auction_document["current_stage"] = len(self.auction_document["stages"]) - 2

    def end_bids_stage(self, switch_to_round=None):
        self.generate_request_id()
        self.bids_actions.acquire()
        self.get_auction_document()
        LOGGER.info(
            '---------------- End Bids Stage ----------------',
            extra={"JOURNAL_REQUEST_ID": self.request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SERVICE_END_BID_STAGE}
        )

        self.current_round = self.get_round_number(
            self.auction_document["current_stage"]
        )
        self.current_stage = self.auction_document["current_stage"]

        if self.approve_bids_information():
            LOGGER.info("Approved bid on current stage")
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

        LOGGER.info('---------------- Start stage {0} ----------------'.format(
            self.auction_document["current_stage"]),
            extra={"JOURNAL_REQUEST_ID": self.request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SERVICE_START_STAGE}
        )
        self.save_auction_document()
        if self.auction_document["stages"][self.auction_document["current_stage"]]['type'] == 'pre_announcement':
            self.end_auction()
        self.bids_actions.release()
        if self.auction_document["current_stage"] == (len(self.auction_document["stages"]) - 1):
            self._end_auction_event.set()

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

    def prepare_auction_stages(self):
        # Initital Bids
        self.auction_document['auction_type'] = 'meat' if self.features else 'default'

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
        LOGGER.info('---------------- Start stage {0} ----------------'.format(
            self.auction_document["current_stage"]),
            extra={"JOURNAL_REQUEST_ID": self.request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SERVICE_START_NEXT_STAGE}
        )


class AuctionRulerMixin(object):

    def schedule_auction(self):
        self.generate_request_id()
        self.get_auction_document()
        self.get_auction_document()
        if self.debug:
            LOGGER.info("Get _auction_data from auction_document")
            self._auction_data = self.auction_document.get('test_auction_data', {})
        self.get_auction_info()
        self.prepare_audit()
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
        LOGGER.info(
            "Prepare server ...",
            extra={"JOURNAL_REQUEST_ID": self.request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SERVICE_PREPARE_SERVER}
        )
        self.server = run_server(self, self.convert_datetime(self.auction_document['stages'][-2]['start']), LOGGER)

    def wait_to_end(self):
        self._end_auction_event.wait()
        LOGGER.info("Stop auction worker",
                    extra={"JOURNAL_REQUEST_ID": self.request_id,
                           "MESSAGE_ID": AUCTION_WORKER_SERVICE_STOP_AUCTION_WORKER})

    def start_auction(self, switch_to_round=None):
        self.generate_request_id()
        self.audit['timeline']['auction_start']['time'] = datetime.now(tzlocal()).isoformat()
        LOGGER.info(
            '---------------- Start auction ----------------',
            extra={"JOURNAL_REQUEST_ID": self.request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SERVICE_START_AUCTION}
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
        LOGGER.info(
            '---------------- End First Pause ----------------',
            extra={"JOURNAL_REQUEST_ID": self.request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SERVICE_END_FIRST_PAUSE}
        )
        self.bids_actions.acquire()
        self.get_auction_document()

        if isinstance(switch_to_round, int):
            self.auction_document["current_stage"] = switch_to_round
        else:
            self.auction_document["current_stage"] += 1

        self.save_auction_document()
        self.bids_actions.release()

    def end_auction(self):
        LOGGER.info(
            '---------------- End auction ----------------',
            extra={"JOURNAL_REQUEST_ID": self.request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SERVICE_END_AUCTION}
        )
        LOGGER.debug("Stop server", extra={"JOURNAL_REQUEST_ID": self.request_id})
        if self.server:
            self.server.stop()
        LOGGER.debug(
            "Clear mapping", extra={"JOURNAL_REQUEST_ID": self.request_id}
        )
        delete_mapping(self.worker_defaults,
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
        LOGGER.debug(' '.join((
            'Document in end_stage: \n', yaml_dump(dict(self.auction_document))
        )), extra={"JOURNAL_REQUEST_ID": self.request_id})
        self.approve_audit_info_on_announcement()
        LOGGER.info('Audit data: \n {}'.format(yaml_dump(self.audit)), extra={"JOURNAL_REQUEST_ID": self.request_id})
        if self.debug:
            LOGGER.debug(
                'Debug: put_auction_data disabled !!!',
                extra={"JOURNAL_REQUEST_ID": self.request_id}
            )
            sleep(10)
            self.save_auction_document()
        else:
            if self.put_auction_data():
                self.save_auction_document()
        LOGGER.debug(
            "Fire 'stop auction worker' event",
            extra={"JOURNAL_REQUEST_ID": self.request_id}
        )

    def cancel_auction(self):
        self.generate_request_id()
        if self.get_auction_document():
            LOGGER.info("Auction {} canceled".format(self.auction_doc_id),
                        extra={'MESSAGE_ID': AUCTION_WORKER_SERVICE_AUCTION_CANCELED})
            self.auction_document["current_stage"] = -100
            self.auction_document["endDate"] = datetime.now(tzlocal()).isoformat()
            LOGGER.info("Change auction {} status to 'canceled'".format(self.auction_doc_id),
                        extra={'MESSAGE_ID': AUCTION_WORKER_SERVICE_AUCTION_STATUS_CANCELED})
            self.save_auction_document()
        else:
            LOGGER.info("Auction {} not found".format(self.auction_doc_id),
                        extra={'MESSAGE_ID': AUCTION_WORKER_SERVICE_AUCTION_NOT_FOUND})

    def reschedule_auction(self):
        self.generate_request_id()
        if self.get_auction_document():
            LOGGER.info("Auction {} has not started and will be rescheduled".format(self.auction_doc_id),
                        extra={'MESSAGE_ID': AUCTION_WORKER_SERVICE_AUCTION_RESCHEDULE})
            self.auction_document["current_stage"] = -101
            self.save_auction_document()
        else:
            LOGGER.info("Auction {} not found".format(self.auction_doc_id),
                        extra={'MESSAGE_ID': AUCTION_WORKER_SERVICE_AUCTION_NOT_FOUND})
