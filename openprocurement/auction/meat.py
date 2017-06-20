import logging
import sys

from datetime import datetime, timedelta
from copy import deepcopy
from dateutil.tz import tzlocal
from zope.interface import implementer
from urlparse import urljoin
from couchdb import Database, Session
from gevent.event import Event
from gevent.lock import BoundedSemaphore
from requests import Session as RequestsSession
from fractions import Fraction
from barbecue import cooking, calculate_coeficient

from openprocurement.auction.systemd_msgs_ids import (
    AUCTION_WORKER_SERVICE_START_AUCTION,
    AUCTION_WORKER_BIDS_LATEST_BID_CANCELLATION,
    AUCTION_WORKER_API_AUCTION_CANCEL,
    AUCTION_WORKER_API_AUCTION_NOT_EXIST,
    AUCTION_WORKER_SERVICE_NUMBER_OF_BIDS
    )
from openprocurement.auction.utils import\
    filter_amount, get_latest_bid_for_bidder, sorting_by_amount,\
    sorting_start_bids_by_amount, get_tender_data

from openprocurement.auction.interfaces import IAuctionWorker
from openprocurement.auction.services import\
    DBServiceMixin, RequestIDServiceMixin, AuditServiceMixin,\
    DateTimeServiceMixin, BiddersServiceMixin, PostAuctionServiceMixin,\
    StagesServiceMixin, AuctionRulerMixin, ROUNDS, PAUSE_SECONDS,\
    BIDS_SECONDS, BIDS_KEYS_FOR_COPY, FIRST_PAUSE_SECONDS
from openprocurement.auction.templates import prepare_bids_stage,\
    prepare_service_stage, prepare_initial_bid_stage


LOGGER = logging.getLogger('Auction Worker')


class MeatDBServiceMixin(DBServiceMixin):

    def get_auction_info(self, prepare=False):
        if not self.debug:
            if prepare:
                self._auction_data = get_tender_data(
                    self.tender_url,
                    request_id=self.request_id,
                    session=self.session
                )
            else:
                self._auction_data = {'data': {}}
            auction_data = get_tender_data(
                self.tender_url + '/auction',
                user=self.worker_defaults["TENDERS_API_TOKEN"],
                request_id=self.request_id,
                session=self.session
            )
            if auction_data:
                self._auction_data['data'].update(auction_data['data'])
                self.startDate = self.convert_datetime(self._auction_data['data']['auctionPeriod']['startDate'])
                del auction_data
            else:
                self.get_auction_document()
                if self.auction_document:
                    self.auction_document["current_stage"] = -100
                    self.save_auction_document()
                    LOGGER.warning("Cancel auction: {}".format(
                        self.auction_doc_id
                    ), extra={"JOURNAL_REQUEST_ID": self.request_id,
                              "MESSAGE_ID": AUCTION_WORKER_API_AUCTION_CANCEL})
                else:
                    LOGGER.error("Auction {} not exists".format(
                        self.auction_doc_id
                    ), extra={"JOURNAL_REQUEST_ID": self.request_id,
                              "MESSAGE_ID": AUCTION_WORKER_API_AUCTION_NOT_EXIST})
                self._end_auction_event.set()
                sys.exit(1)
        self.bidders = [bid["id"]
                        for bid in self._auction_data["data"]["bids"]
                        if bid.get('status', 'active') == 'active']
        self.bidders_count = len(self.bidders)
        LOGGER.info("Bidders count: {}".format(self.bidders_count),
                    extra={"JOURNAL_REQUEST_ID": self.request_id,
                           "MESSAGE_ID": AUCTION_WORKER_SERVICE_NUMBER_OF_BIDS})
        self.rounds_stages = []
        for stage in range((self.bidders_count + 1) * ROUNDS + 1):
            if (stage + self.bidders_count) % (self.bidders_count + 1) == 0:
                self.rounds_stages.append(stage)
        self.mapping = {}
        self.startDate = self.convert_datetime(
            self._auction_data['data']['auctionPeriod']['startDate']
        )
        if "features" in self._auction_data["data"]:
            self.features = self._auction_data["data"]["features"]

        if not prepare:
            self.bidders_data = []
            if self.features:
                self.bidders_features = {}
                self.bidders_coeficient = {}
                self.features = self._auction_data["data"]["features"]
                for bid in self._auction_data["data"]["bids"]:
                    if bid.get('status', 'active') == 'active':
                        self.bidders_features[bid["id"]] = bid["parameters"]
                        self.bidders_coeficient[bid["id"]] = calculate_coeficient(self.features, bid["parameters"])
            else:
                self.bidders_features = None
                self.features = None

            for bid in self._auction_data['data']['bids']:
                if bid.get('status', 'active') == 'active':
                    self.bidders_data.append({
                        'id': bid['id'],
                        'date': bid['date'],
                        'value': bid['value']
                    })
                    if self.features:
                        self.bidders_features[bid["id"]] = bid["parameters"]
                        self.bidders_coeficient[bid["id"]] = calculate_coeficient(self.features, bid["parameters"])
            self.bidders_count = len(self.bidders_data)

            for index, uid in enumerate(self.bidders_data):
                self.mapping[self.bidders_data[index]['id']] = str(index + 1)

    def prepare_public_document(self):
        public_document = super(MeatDBServiceMixin, self).prepare_public_document()
        not_last_stage = self.auction_document["current_stage"] not in\
                (len(self.auction_document["stages"]) - 1,
                 len(self.auction_document["stages"]) - 2,)
        if not_last_stage:
            for stage_name in ['initial_bids', 'stages', 'results']:
                public_document[stage_name] = map(
                    filter_amount,
                    public_document[stage_name]
                )
        return public_document


class MeatAuditAuditServiceMixin(AuditServiceMixin):

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
            self.audit['timeline'][round_label][turn_label]["amount_features"] = str(
                self.auction_document["stages"][self.current_stage].get("amount_features")
            )
            self.audit['timeline'][round_label][turn_label]["coeficient"] = str(
                self.auction_document["stages"][self.current_stage].get("coeficient")
            )


class MeatBiddersServiceMixin(BiddersServiceMixin):
    def filter_bids_keys(self, bids):
        filtered_bids_data = []
        for bid_info in bids:
            bid_info_result = {key: bid_info[key] for key in BIDS_KEYS_FOR_COPY}
            bid_info_result['amount_features'] = bid_info['amount_features']
            bid_info_result['coeficient'] = bid_info['coeficient']
            bid_info_result["bidder_name"] = self.mapping[bid_info_result['bidder_id']]
            filtered_bids_data.append(bid_info_result)
        return filtered_bids_data

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
            bid_info['amount_features'] = str(Fraction(bid_info['amount']) / self.bidders_coeficient[bid_info['bidder_id']])
            self.auction_document["stages"][self.current_stage] = prepare_bids_stage(
                self.auction_document["stages"][self.current_stage],
                bid_info
            )
            self.auction_document["stages"][self.current_stage]["changed"] = True

            return True
        else:
            return False


class MeatStagesServiceMixin(StagesServiceMixin):

    def prepare_auction_stages_fast_forward(self):
        # TODO: METHODS ARE SAME!!
        self.auction_document['auction_type'] = 'meat'
        bids = deepcopy(self.bidders_data)
        self.auction_document["initial_bids"] = []
        bids_info = sorting_start_bids_by_amount(bids, features=self.features)
        for index, bid in enumerate(bids_info):
            amount = bid["value"]["amount"]
            amount_features = cooking(
                amount,
                self.features, self.bidders_features[bid["id"]]
            )
            coeficient = self.bidders_coeficient[bid["id"]]

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

    def prepare_auction_stages(self):
        # Initital Bids
        self.auction_document['auction_type'] = 'meat'

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


class MeatAuctionRulerMixin(AuctionRulerMixin):
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
        # TODO:
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


@implementer(IAuctionWorker)
class MeatAuction(MeatDBServiceMixin,
                  RequestIDServiceMixin,
                  MeatAuditAuditServiceMixin,
                  MeatBiddersServiceMixin,
                  DateTimeServiceMixin,
                  StagesServiceMixin,
                  PostAuctionServiceMixin,
                  MeatAuctionRulerMixin):
    """Auction Worker Class"""

    def __init__(self, tender_id,
                 worker_defaults={},
                 auction_data={},
                 lot_id=None,
                 activate=False):
        super(MeatAuction, self).__init__()
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
        self.activate = activate
        if auction_data:
            self.debug = True
            LOGGER.setLevel(logging.DEBUG)
            self._auction_data = auction_data
        else:
            self.debug = False
        self._end_auction_event = Event()
        self.bids_actions = BoundedSemaphore()
        self.session = RequestsSession()
        self.worker_defaults = worker_defaults
        if self.worker_defaults.get('with_document_service', False):
            self.session_ds = RequestsSession()
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
