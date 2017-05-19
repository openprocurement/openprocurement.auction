from gevent import monkey
monkey.patch_all()


try:
    import urllib3.contrib.pyopenssl
    urllib3.contrib.pyopenssl.inject_into_urllib3()
except ImportError:
    pass

import logging
import logging.config
import os
import argparse
import iso8601

from datetime import datetime, timedelta
from time import sleep, mktime, time
from urlparse import urljoin

from apscheduler.schedulers.gevent import GeventScheduler
from gevent.queue import Queue, Empty
from gevent.subprocess import check_call

from couchdb import Database, Session
from dateutil.tz import tzlocal
from systemd_msgs_ids import (
    DATA_BRIDGE_PLANNING_START_BRIDGE,
    DATA_BRIDGE_PLANNING_DATA_SYNC,
    DATA_BRIDGE_PLANNING_TENDER_SKIP,
    DATA_BRIDGE_PLANNING_TENDER_ALREADY_PLANNED,
    DATA_BRIDGE_PLANNING_LOT_SKIP,
    DATA_BRIDGE_PLANNING_LOT_ALREADY_PLANNED,
    DATA_BRIDGE_PLANNING_SKIPED_TEST,
    DATA_BRIDGE_PLANNING_SELECT_TENDER,
    DATA_BRIDGE_PLANNING_DATA_SYNC_RESUME,
    DATA_BRIDGE_PLANNING_COUCH_FEED,
    DATA_BRIDGE_PLANNING_COUCH_DATA_SYNC,
    DATA_BRIDGE_RE_PLANNING_START_BRIDGE,
    DATA_BRIDGE_RE_PLANNING_TENDER_ALREADY_PLANNED,
    DATA_BRIDGE_RE_PLANNING_LOT_ALREADY_PLANNED,
    DATA_BRIDGE_RE_PLANNING_FINISHED
)
from openprocurement_client.sync import get_tenders, ResourceFeeder
from yaml import load
from .design import endDate_view, startDate_view, PreAnnounce_view
from .utils import do_until_success
from openprocurement.auction.interfaces import IAuctionDataBridge, IResourceListingItemFactory
from zope.interface import implements
from openprocurement.auction.content import init_auction
from zope.component import queryUtility

SIMPLE_AUCTION_TYPE = 0
SINGLE_LOT_AUCTION_TYPE = 1


DEFAULT_RETRIEVERS_PARAMS = {
    'down_requests_sleep': 0.01,
    'up_requests_sleep': 0.01,
    'up_wait_sleep': 30,
    'queue_size': 100
}


logger = logging.getLogger(__name__)


class BatchResourceFeeder(ResourceFeeder):

    def handle_response_data(self, data):
        self.queue.put(data)
        # self.idle()

class AuctionsDataBridge(object):
    implements(IAuctionDataBridge)
    logger = logger
    startDate_view = startDate_view
    """Auctions Data Bridge"""

    def __init__(self, config):
        super(AuctionsDataBridge, self).__init__()
        self.config = config
        self.tenders_ids_list = []
        self.tz = tzlocal()

        self.couch_url = urljoin(
            self.config_get('couch_url'),
            self.config_get('auctions_db')
        )
        self.db = Database(self.couch_url,
                           session=Session(retry_delays=range(10)))
        init_auction()

    def config_get(self, name):
        return self.config.get('main').get(name)

    def make_listing_item(self, item):
        factory = queryUtility(IResourceListingItemFactory, item.get('procurementMethodType', ''))
        if factory:
            return factory(self, item)

    def get_teders_list(self, re_planning=False):
        last = datetime.now()
        period = timedelta(seconds=10)
        count = 0
        feeder = BatchResourceFeeder(host=self.config_get('tenders_api_server'),
                                version=self.config_get('tenders_api_version'),
                                key='', extra_params={'opt_fields': 'status,auctionPeriod,lots,procurementMethodType', 'limit': '1000', 'mode': '_all_'},
                                retrievers_params=DEFAULT_RETRIEVERS_PARAMS)
        queue = feeder.run_feeder()
        while 1:
            # print queue
            batch = queue.get()
        # for item in get_tenders(host=self.config_get('tenders_api_server'),
        #                         version=self.config_get('tenders_api_version'),
        #                         key='', extra_params={'opt_fields': 'status,auctionPeriod,lots,procurementMethodType', 'limit': 1000, 'mode': '_all_'},
        #                         retrievers_params=DEFAULT_RETRIEVERS_PARAMS):
            #####
            # Make ListingItemData
            # Adapt ListingItemData to
            #####
            # print len(batch)
            for item in batch:
                count += 1
                if datetime.now() - last > period:
                    print count
                    last = datetime.now()
                resource_item = self.make_listing_item(item)
                if not resource_item:
                    continue
                for auction_worker_params in resource_item.iter_planning():
                    yield auction_worker_params


    def start_auction_worker_cmd(self, cmd, tender_id, with_api_version=None, lot_id=None):
        # params = [self.config_get('auction_worker'),
        #           cmd, tender_id,
        #           self.config_get('auction_worker_config')]
        # if lot_id:
        #     params += ['--lot', lot_id]
        #
        # if with_api_version:
        #     params += ['--with_api_version', with_api_version]
        # result = do_until_success(
        #     check_call,
        #     args=(params,),
        # )
        #
        # logger.info("Auction command {} result: {}".format(params[1], result))
        logger.error("Auction command ")

    def run(self):
        logger.info('Start Auctions Bridge',
                    extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING_START_BRIDGE})
        logger.info('Start data sync...',
                    extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING_DATA_SYNC})
        for planning_data in self.get_teders_list():
            if len(planning_data) == 1:
                logger.info('Tender {0} selected for planning'.format(*planning_data))
                self.start_auction_worker_cmd('planning', planning_data[0])
            elif len(planning_data) == 2:
                logger.info('Lot {1} of tender {0} selected for planning'.format(*planning_data))
                self.start_auction_worker_cmd('planning', planning_data[0], lot_id=planning_data[1])

    def run_re_planning(self):
        pass
        # self.re_planning = True
        # self.offset = ''
        # logger.info('Start Auctions Bridge for re-planning...',
        #             extra={'MESSAGE_ID': DATA_BRIDGE_RE_PLANNING_START_BRIDGE})
        # for tender_item in self.get_teders_list(re_planning=True):
        #     logger.debug('Tender {} selected for re-planning'.format(tender_item))
        #     for planning_data in self.get_teders_list():
        #         if len(planning_data) == 1:
        #             logger.info('Tender {0} selected for planning'.format(*planning_data))
        #             self.start_auction_worker_cmd('planning', planning_data[0])
        #         elif len(planning_data) == 2:
        #             logger.info('Lot {1} of tender {0} selected for planning'.format(*planning_data))
        #             self.start_auction_worker_cmd('planning', planning_data[0], lot_id=planning_data[1])
        #         self.tenders_ids_list.append(tender_item['id'])
        #     sleep(1)
        # logger.info("Re-planning auctions finished",
        #             extra={'MESSAGE_ID': DATA_BRIDGE_RE_PLANNING_FINISHED})


def main():
    parser = argparse.ArgumentParser(description='---- Auctions Bridge ----')
    parser.add_argument('config', type=str, help='Path to configuration file')
    parser.add_argument(
        '--re-planning', action='store_true', default=False,
        help='Not ignore auctions which already scheduled')
    params = parser.parse_args()
    if os.path.isfile(params.config):
        with open(params.config) as config_file_obj:
            config = load(config_file_obj.read())
        logging.config.dictConfig(config)
        if params.re_planning:
            AuctionsDataBridge(config).run_re_planning()
        else:
            AuctionsDataBridge(config).run()


##############################################################

if __name__ == "__main__":
    main()
