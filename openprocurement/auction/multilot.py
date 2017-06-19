import logging
from copy import deepcopy
from zope.interface import implementer
from urlparse import urljoin
from couchdb import Database, Session
from gevent.event import Event
from gevent.lock import BoundedSemaphore
from requests import Session as RequestsSession

from openprocurement.auction.systemd_msgs_ids import AUCTION_WORKER_API_AUCTION_RESULT_NOT_APPROVED
from openprocurement.auction.tenders_types import multiple_lots_tenders
from openprocurement.auction.interfaces import IAuctionWorker
from openprocurement.auction.services import\
    DBServiceMixin, RequestIDServiceMixin, AuditServiceMixin,\
    DateTimeServiceMixin, BiddersServiceMixin, PostAuctionServiceMixin,\
    StagesServiceMixin, AuctionRulerMixin, ROUNDS


LOGGER = logging.getLogger('Auction Worker')


class MultilotDBServiceMixin(DBServiceMixin):

    def get_auction_info(self, prepare=False):
        multiple_lots_tenders.get_auction_info(self, prepare)

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
                results = multiple_lots_tenders.post_results_data(self, with_auctions_results=False)
                return 0
            elif submissionMethodDetails == 'quick(mode:fast-forward)':
                self.auction_document = multiple_lots_tenders.prepare_auction_document(self)
                if not self.debug:
                    self.set_auction_and_participation_urls()
                self.get_auction_info()
                self.prepare_auction_stages_fast_forward()
                self.save_auction_document()
                multiple_lots_tenders.post_results_data(self, with_auctions_results=False)
                self.save_auction_document()
                return

        self.auction_document = multiple_lots_tenders.prepare_auction_document(self)

        self.save_auction_document()
        if not self.debug:
            self.set_auction_and_participation_urls()


class MultilotAuditServiceMixin(AuditServiceMixin):
    def prepare_audit(self):
        self.audit = {
            "id": self.auction_doc_id,
            "tenderId": self._auction_data["data"].get("tenderID", ""),
            "tender_id": self.tender_id,
            "timeline": {
                "auction_start": {
                    "initial_bids": []
                }
            },
            "lot_id": self.lot_id
        }
        for round_number in range(1, ROUNDS + 1):
            self.audit['timeline']['round_{}'.format(round_number)] = {}


class MultilotBiddersServiceMixin(BiddersServiceMixin):
    def set_auction_and_participation_urls(self):
        multiple_lots_tenders.prepare_auction_and_participation_urls(self)


class MultilotPostAuctionServiceMixin(PostAuctionServiceMixin):
    def put_auction_data(self):
        if self.worker_defaults.get('with_document_service', False):
            doc_id = self.upload_audit_file_with_document_service()
        else:
            doc_id = self.upload_audit_file_without_document_service()

        results = multiple_lots_tenders.post_results_data(self)

        if results:
            bids_information = None
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
        multiple_lots_tenders.announce_results_data(self, None)
        self.save_auction_document()



@implementer(IAuctionWorker)
class Auction(MultilotDBServiceMixin,
              RequestIDServiceMixin,
              MultilotAuditServiceMixin,
              MultilotBiddersServiceMixin,
              DateTimeServiceMixin,
              StagesServiceMixin,
              MultilotPostAuctionServiceMixin,
              AuctionRulerMixin):
    """Auction Worker Class"""

    def __init__(self, tender_id,
                 worker_defaults={},
                 auction_data={},
                 lot_id=None,
                 activate=False):
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
