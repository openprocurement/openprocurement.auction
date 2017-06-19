# -*- coding: utf-8 -*-
from gevent import monkey
monkey.patch_all()

import argparse
import logging
import logging.config
import json
import sys
import os
import re
from urlparse import urljoin
from couchdb import Database, Session
from gevent.event import Event
from gevent.lock import BoundedSemaphore
from requests import Session as RequestsSession


MULTILINGUAL_FIELDS = ["title", "description"]
ADDITIONAL_LANGUAGES = ["ru", "en"]
PLANNING_FULL = "full"
PLANNING_PARTIAL_DB = "partial_db"
PLANNING_PARTIAL_CRON = "partial_cron"
BIDS_KEYS_FOR_COPY = ("bidder_id", "amount", "time")
TIMER_STAMP = re.compile(
    r"OnCalendar=(?P<year>[0-9][0-9][0-9][0-9])"
    r"-(?P<mon>[0-9][0-9])-(?P<day>[0123][0-9]) "
    r"(?P<hour>[0-2][0-9]):(?P<min>[0-5][0-9]):(?P<sec>[0-5][0-9])"
)
logger = logging.getLogger('Auction Worker')


from openprocurement.auction.services import\
    DBServiceMixin, RequestIDServiceMixin, AuditServiceMixin,\
    DateTimeServiceMixin, BiddersServiceMixin, PostAuctionServiceMixin,\
    StagesServiceMixin, AuctionRulerMixin, SCHEDULER



class Auction(DBServiceMixin,
              RequestIDServiceMixin,
              AuditServiceMixin,
              BiddersServiceMixin,
              DateTimeServiceMixin,
              StagesServiceMixin,
              PostAuctionServiceMixin,
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
            logger.setLevel(logging.DEBUG)
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


def main():
    parser = argparse.ArgumentParser(description='---- Auction ----')
    parser.add_argument('cmd', type=str, help='')
    parser.add_argument('auction_doc_id', type=str, help='auction_doc_id')
    parser.add_argument('auction_worker_config', type=str,
                        help='Auction Worker Configuration File')
    parser.add_argument('--auction_info', type=str, help='Auction File')
    parser.add_argument('--auction_info_from_db', type=str, help='Get auction data from local database')
    parser.add_argument('--with_api_version', type=str, help='Tender Api Version')
    parser.add_argument('--lot', type=str, help='Specify lot in tender', default=None)
    parser.add_argument('--planning_procerude', type=str, help='Override planning procerude',
                        default=None, choices=[None, PLANNING_FULL, PLANNING_PARTIAL_DB, PLANNING_PARTIAL_CRON])


    args = parser.parse_args()

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

    if args.auction_info_from_db:
        auction_data = {'mode': 'test'}
    elif args.auction_info:
        auction_data = json.load(open(args.auction_info))
    else:
        auction_data = None

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
        auction.prepare_auction_document()
    elif args.cmd == 'announce':
        auction.post_announce()
    elif args.cmd == 'cancel':
        auction.cancel_auction()
    elif args.cmd == 'reschedule':
        auction.reschedule_auction()


if __name__ == "__main__":
    main()
