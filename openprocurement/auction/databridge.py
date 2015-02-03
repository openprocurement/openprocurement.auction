import argparse
import logging
import logging.config
import requests
import os
from time import sleep
from urlparse import urljoin

from datetime import datetime
from pytz import timezone
from subprocess import check_output
from couchdb.client import Database
from time import time
import iso8601
from .design import endDate_view
from .utils import do_until_success, generate_request_id
from yaml import load

logger = logging.getLogger(__name__)


class AuctionsDataBridge(object):
    """docstring for AuctionsDataBridge"""
    def __init__(self, config, ignore_exists):
        super(AuctionsDataBridge, self).__init__()
        self.config = config
        self.ignore_exists = ignore_exists
        self.tenders_url = urljoin(
            self.config_get('tenders_api_server'),
            '/api/{}/tenders'.format(
                self.config_get('tenders_api_version')
            )
        )
        self.tz = timezone('Europe/Kiev')
        self.couch_url = urljoin(
            self.config_get('couch_url'),
            self.config_get('auctions_db')
        )
        self.db = Database(self.couch_url)
        self.url = self.tenders_url

    def config_get(self, name):
        return self.config.get('main').get(name)

    def tender_url(self, tender_id):
        return urljoin(self.tenders_url, 'tenders/{}/auction'.format(tender_id))

    def get_teders_list(self):
        while True:
            params = {'offset': self.offset,
                      'opt_fields': 'status,auctionPeriod',
                      'mode': '_all_'}
            request_id = generate_request_id(prefix=b'data-bridge-req-')
            logger.debug('Start request to {}, params: {}'.format(
                self.url, params),
                extra={"JOURNAL_REQUEST_ID": request_id})

            response = requests.get(self.url, params=params,
                                    headers={'content-type': 'application/json',
                                             'X-Client-Request-ID': request_id})

            logger.debug('Request response: {}'.format(response.status_code))
            if response.ok:
                response_json = response.json()
                if len(response_json['data']) == 0:
                    logger.info("Change offset date to {}".format(response_json['next_page']['offset']))
                    self.offset = response_json['next_page']['offset']
                    break
                for item in response_json['data']:
                    if 'auctionPeriod' in item \
                            and 'startDate' in item['auctionPeriod'] \
                            and 'endDate' not in item['auctionPeriod'] \
                            and item['status'] == "active.auction":

                        date = iso8601.parse_date(item['auctionPeriod']['startDate'])
                        date = date.astimezone(self.tz)
                        if datetime.now(self.tz) > date:
                            continue
                        if self.ignore_exists:
                            future_auctions = endDate_view(
                                self.db, startkey=time() * 1000
                            )
                            if item["id"] in [i.id for i in future_auctions]:
                                logger.warning(
                                    "Tender with id {} already scheduled".format(item["id"]),
                                    extra={"JOURNAL_REQUEST_ID": request_id}
                                )
                                continue
                        yield item
                    if item['status'] == "cancelled":
                        future_auctions = endDate_view(
                            self.db, startkey=time() * 1000
                        )
                        if item["id"] in [i.id for i in future_auctions]:
                            logger.info("Tender {} canceled".format(item["id"]))
                            auction_document = self.db[item["id"]]
                            auction_document["current_stage"] = -100
                            auction_document["endDate"] = datetime.now(self.tz).isoformat()
                            self.db.save(auction_document)
                            logger.info(
                                "Change auction {} status to 'canceled'".format(item["id"]),
                                extra={"JOURNAL_REQUEST_ID": request_id}
                            )

                logger.info(
                    "Change offset date to {}".format(response_json['next_page']['offset']),
                    extra={"JOURNAL_REQUEST_ID": request_id}
                )
                self.offset = response_json['next_page']['offset']
            else:
                sleep(2)

    def start_auction_worker(self, tender_item):
        result = do_until_success(
            check_output,
            args=([self.config_get('auction_worker'),
                   'planning', str(tender_item['id']),
                   self.config_get('auction_worker_config')],),
        )
        logger.info("Auction planning: {}".format(result))

    def run(self):
        logger.info('Start Auctions Bridge')
        self.offset = ''
        while True:
            logger.info('Start data sync...')
            for tender_item in self.get_teders_list():
                logger.debug('Item {}'.format(tender_item))
                self.start_auction_worker(tender_item)
                sleep(3)
            logger.info('Wait...')
            sleep(100)


def main():
    parser = argparse.ArgumentParser(description='---- Auctions Bridge ----')
    parser.add_argument('config', type=str, help='Path to configuration file')
    parser.add_argument(
        '--ignore-exists', action='store_false', default=True,
        help='Not ignore auctions which already scheduled')
    params = parser.parse_args()
    if os.path.isfile(params.config):
        with open(params.config) as config_file_obj:
            config = load(config_file_obj.read())
        logging.config.dictConfig(config)
        AuctionsDataBridge(config, params.ignore_exists).run()


##############################################################

if __name__ == "__main__":
    main()
