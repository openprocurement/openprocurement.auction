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

from datetime import datetime
from subprocess import check_call
from time import sleep, mktime, time
from urlparse import urljoin

from couchdb import Database, Session
from dateutil.tz import tzlocal
from openprocurement_client.client import Client as ApiClient
from pkg_resources import parse_version
from systemd_msgs_ids import (
    DATA_BRIDGE_RE_PLANNING,
    DATA_BRIDGE_PLANNING,
    DATA_BRIDGE_PLANNING_PROCESS
)
from yaml import load
from .design import endDate_view, startDate_view, PreAnnounce_view
from .utils import do_until_success, generate_request_id

SIMPLE_AUCTION_TYPE = 0
SINGLE_LOT_AUCTION_TYPE = 1

MULTILOT_AUCTION_ID = "{0[id]}_{1[id]}" # {TENDER_ID}_{LOT_ID}

logger = logging.getLogger(__name__)


class AuctionsDataBridge(object):

    """Auctions Data Bridge"""

    def __init__(self, config):
        super(AuctionsDataBridge, self).__init__()
        self.config = config
        self.tenders_ids_list = []
        self.client = ApiClient(
            '',
            host_url=self.config_get('tenders_api_server'),
            api_version=self.config_get('tenders_api_version'),
            resource='auctions'
        )
        params = {'opt_fields': 'status,auctionPeriod', 'mode': '_all_'}
        if parse_version(self.config_get('tenders_api_version')) > parse_version('0.9'):
            params['opt_fields'] += ',lots'
        self.client.params.update(params)
        self.tz = tzlocal()
        self.couch_url = urljoin(
            self.config_get('couch_url'),
            self.config_get('auctions_db')
        )
        self.db = Database(self.couch_url,
                           session=Session(retry_delays=range(10)))

    def config_get(self, name):
        return self.config.get('main').get(name)

    def get_teders_list(self, re_planning=False):
        while True:
            request_id = generate_request_id(prefix=b'data-bridge-req-')
            self.client.headers.update({'X-Client-Request-ID': request_id})
            tenders_list = list(self.client.get_tenders())
            if tenders_list:
                logger.info("Client params: {}".format(self.client.params))
                for item in tenders_list:
                    if item['status'] == "active.auction":
                        if 'auctionPeriod' in item and 'startDate' in item['auctionPeriod'] \
                                and 'endDate' not in item['auctionPeriod']:

                            start_date = iso8601.parse_date(item['auctionPeriod']['startDate'])
                            start_date = start_date.astimezone(self.tz)
                            auctions_start_in_date = startDate_view(
                                self.db,
                                key=(mktime(start_date.timetuple()) + start_date.microsecond / 1E6) * 1000
                            )
                            if datetime.now(self.tz) > start_date:
                                logger.info("Tender {} start date in past. Skip it for planning".format(item['id']),
                                            extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING})
                                continue
                            if re_planning and item['id'] in self.tenders_ids_list:
                                logger.info("Tender {} already planned while replanning".format(item['id']),
                                            extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING})
                                continue
                            elif not re_planning and [row.id for row in auctions_start_in_date.rows if row.id == item['id']]:
                                logger.info("Tender {} already planned on same date".format(item['id']),
                                            extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING})
                                continue
                            yield (str(item['id']), )
                        elif 'lots' in item:
                            for lot in item['lots']:
                                if lot["status"] == "active" and 'startDate' in lot['auctionPeriod'] \
                                        and 'endDate' not in lot['auctionPeriod']:
                                    start_date = iso8601.parse_date(lot['auctionPeriod']['startDate'])
                                    start_date = start_date.astimezone(self.tz)
                                    auctions_start_in_date = startDate_view(
                                        self.db,
                                        key=(mktime(start_date.timetuple()) + start_date.microsecond / 1E6) * 1000
                                    )
                                    if datetime.now(self.tz) > start_date:
                                        logger.info(
                                            "Start date for lot {} in tender {} is in past. Skip it for planning".format(
                                                lot['id'], item['id']),
                                            extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING}
                                        )
                                        continue
                                    auction_id = MULTILOT_AUCTION_ID.format(item, lot)
                                    if re_planning and auction_id in self.tenders_ids_list:
                                        logger.info("Tender {} already planned while replanning".format(auction_id),
                                                    extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING})
                                        continue
                                    elif not re_planning and [row.id for row in auctions_start_in_date.rows if row.id == auction_id]:
                                        logger.info("Tender {} already planned on same date".format(auction_id),
                                                    extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING})
                                        continue
                                    yield (str(item["id"]), str(lot["id"]), )
                    if item['status'] == "active.qualification" and 'lots' in item:
                        for lot in item['lots']:
                            if lot["status"] == "active":
                                is_pre_announce = PreAnnounce_view(self.db)
                                auction_id = MULTILOT_AUCTION_ID.format(item, lot)
                                if [row.id for row in is_pre_announce.rows if row.id == auction_id]:
                                    self.start_pre_announce(item['id'], lot_id=lot['id'],)
                    if item['status'] == "cancelled":
                        future_auctions = endDate_view(
                            self.db, startkey=time() * 1000
                        )
                        if 'lots' in item:
                            for lot in item['lots']:
                                auction_id = MULTILOT_AUCTION_ID.format(item, lot)
                                if item["id"] in [i.id for i in future_auctions]:
                                    self.cancel_auction(auction_id)
                        else:
                            if item["id"] in [i.id for i in future_auctions]:
                                self.cancel_auction(item["id"])


            else:
                break

    def cancel_auction(self, auction_id):
        logger.info("Auction {} canceled".format(auction_id),
                    extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING})
        auction_document = self.db[auction_id]
        auction_document["current_stage"] = -100
        auction_document["endDate"] = datetime.now(self.tz).isoformat()
        self.db.save(auction_document)
        logger.info("Change auction {} status to 'canceled'".format(auction_id),
                    extra={"JOURNAL_REQUEST_ID": request_id,
                           'MESSAGE_ID': DATA_BRIDGE_PLANNING})


    def start_pre_announce(self, tender_id, with_api_version=None, lot_id=None):
        params = [self.config_get('auction_worker'),
                  'announce', tender_id,
                  self.config_get('auction_worker_config')]
        if lot_id:
            params += ['--lot', lot_id]

        if with_api_version:
            params += ['--with_api_version', with_api_version]
        result = do_until_success(
            check_call,
            args=(params,),
        )
        logger.info("Auction announce command result: {}".format(result),
                    extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING_PROCESS})

    def start_auction_worker(self, tender_id, with_api_version=None, lot_id=None):
        params = [self.config_get('auction_worker'),
                  'planning', tender_id,
                  self.config_get('auction_worker_config')]
        if lot_id:
            params += ['--lot', lot_id]

        if with_api_version:
            params += ['--with_api_version', with_api_version]
        result = do_until_success(
            check_call,
            args=(params,),
        )
        logger.info("Auction planning command result: {}".format(result),
                    extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING_PROCESS})

    def planning_with_couch(self):
        logger.info('Start Auctions Bridge with feed to couchdb',
                    extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING})
        logger.info('Start data sync...',
                    extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING})
        self.planned_tenders = {}
        self.last_seq_id = 0
        while True:
            do_until_success(self.handle_continuous_feed)

    def handle_continuous_feed(self):
        change = self.db.changes(feed='continuous', filter="auctions/by_startDate",
                                 since=self.last_seq_id, include_docs=True)
        for auction_item in change:
            if 'id' in auction_item:
                start_date = auction_item['doc']['stages'][0]['start']
                if auction_item['doc'].get("current_stage", "") == -100:
                    continue

                if auction_item['doc'].get("mode", "") == "test":
                    logger.info('Sciped test auction {}'.format(auction_item['id']),
                                extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING})
                    continue

                if auction_item['id'] in self.planned_tenders and \
                        self.planned_tenders[auction_item['id']] == start_date:
                    logger.debug('Tender {} filtered'.format(auction_item['id']))
                    continue
                logger.info('Tender {} selected for planning'.format(auction_item['id']),
                            extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING})

                if "_" in auction_item['id']:
                    tender_id, lot_id = auction_item['id'].split("_")
                else:
                    tender_id = auction_item['id']
                    lot_id = None

                self.start_auction_worker(
                    tender_id, lot_id=lot_id,
                    with_api_version=auction_item['doc'].get('TENDERS_API_VERSION', None)
                )

                self.planned_tenders[auction_item['id']] = start_date
            elif 'last_seq' in auction_item:
                self.last_seq_id = auction_item['last_seq']

        logger.info('Resume data sync...',
                    extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING})

    def run(self):
        logger.info('Start Auctions Bridge',
                    extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING})
        logger.info('Start data sync...',
                    extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING})
        while True:
            for planning_data in self.get_teders_list():
                if len(planning_data) == 1:
                    logger.info('Tender {0} selected for planning'.format(*planning_data))
                    self.start_auction_worker(planning_data[0])
                elif len(planning_data) == 2:
                    logger.info('Lot {1} of tender {0} selected for planning'.format(*planning_data))
                    self.start_auction_worker(planning_data[0], lot_id=planning_data[1])
            logger.info('Sleep...',
                        extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING})
            sleep(100)
            logger.info('Resume data sync...',
                        extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING})

    def run_re_planning(self):
        self.re_planning = True
        self.offset = ''
        logger.info('Start Auctions Bridge for re-planning...',
                    extra={'MESSAGE_ID': DATA_BRIDGE_RE_PLANNING})
        for tender_item in self.get_teders_list(re_planning=True):
            logger.debug('Tender {} selected for re-planning'.format(tender_item))
            for planning_data in self.get_teders_list():
                if len(planning_data) == 1:
                    logger.info('Tender {0} selected for planning'.format(*planning_data))
                    self.start_auction_worker(planning_data[0])
                elif len(planning_data) == 2:
                    logger.info('Lot {1} of tender {0} selected for planning'.format(*planning_data))
                    self.start_auction_worker(planning_data[0], lot_id=planning_data[1])
                self.tenders_ids_list.append(tender_item['id'])
            sleep(1)
        logger.info("Re-planning auctions finished",
                    extra={'MESSAGE_ID': DATA_BRIDGE_RE_PLANNING})


def main():
    parser = argparse.ArgumentParser(description='---- Auctions Bridge ----')
    parser.add_argument('config', type=str, help='Path to configuration file')
    parser.add_argument(
        '--re-planning', action='store_true', default=False,
        help='Not ignore auctions which already scheduled')
    parser.add_argument(
        '--planning-with-couch', action='store_true', default=False,
        help='Use couchdb for tenders feed')
    params = parser.parse_args()
    if os.path.isfile(params.config):
        with open(params.config) as config_file_obj:
            config = load(config_file_obj.read())
        logging.config.dictConfig(config)
        if params.planning_with_couch:
            AuctionsDataBridge(config).planning_with_couch()
        elif params.re_planning:
            AuctionsDataBridge(config).run_re_planning()
        else:
            AuctionsDataBridge(config).run()


##############################################################

if __name__ == "__main__":
    main()
