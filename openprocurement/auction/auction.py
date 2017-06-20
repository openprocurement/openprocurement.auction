import logging
from zope.interface import implementer
from urlparse import urljoin
from couchdb import Database, Session
from gevent.event import Event
from gevent.lock import BoundedSemaphore
from requests import Session as RequestsSession

from openprocurement.auction.interfaces import IAuctionWorker
from openprocurement.auction.services import\
    DBServiceMixin, RequestIDServiceMixin, AuditServiceMixin,\
    DateTimeServiceMixin, BiddersServiceMixin, PostAuctionServiceMixin,\
    StagesServiceMixin, AuctionRulerMixin


LOGGER = logging.getLogger('Auction Worker')


@implementer(IAuctionWorker)
class Auction(DBServiceMixin,
              RequestIDServiceMixin,
              AuditServiceMixin,
              BiddersServiceMixin,
              DateTimeServiceMixin,
              StagesServiceMixin,
              PostAuctionServiceMixin,
              AuctionRulerMixin):
    """Auction Worker Class"""

    klass = 'default'

    def __init__(self, tender_id,
                 worker_defaults={},
                 auction_data={},
                 lot_id=""):# TODO:
        super(Auction, self).__init__()
        self.generate_request_id()
        self.tender_id = tender_id
        self.auction_doc_id = tender_id
        self.tender_url = urljoin(
            worker_defaults["TENDERS_API_URL"],
            '/api/{0}/tenders/{1}'.format(
                worker_defaults["TENDERS_API_VERSION"], tender_id
            )
        )
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
