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

from yaml import load
from zope.interface import implementer
from pytz import timezone
from gevent import sleep
from gevent.pywsgi import WSGIServer
from datetime import datetime, timedelta

from openprocurement.auction.utils import FeedItem
from openprocurement.auction.core import components
from openprocurement.auction.interfaces import IAuctionsChronograph, IAuctionsManager
from openprocurement.auction.design import sync_design_chronograph
from openprocurement.auction.helpers.chronograph import get_server_name, AuctionScheduler
from openprocurement.auction.helpers.chronograph_http import chronograph_webapp
from openprocurement.auction.helpers.couch import iterview, couchdb_dns_query_settings
from openprocurement.auction.helpers.system import get_lisener


LOGGER = logging.getLogger('Auction Chronograph')


@implementer(IAuctionsChronograph)
class AuctionsChronograph(object):

    def __init__(self, config, *args, **kwargs):
        super(AuctionsChronograph, self).__init__(*args, **kwargs)
        self.config = config
        self.timezone = timezone(config['main']['timezone'])
        self.mapper = components.qA(self, IAuctionsManager)
        self.server_name = get_server_name()
        LOGGER.info('Init node: {}'.format(self.server_name))
        self.init_database()
        self.init_scheduler()
        if config['main'].get('web_app', None):
            self.init_web_app()

    def init_database(self):

        sync_design_chronograph(couchdb_dns_query_settings(
            self.config['main']["couch_url"],
            self.config['main']['auctions_db']
        ))

    def init_scheduler(self):
        self.scheduler = AuctionScheduler(self.server_name, self.config, logger=LOGGER,
                                          timezone=self.timezone)
        self.scheduler.chronograph = self
        self.scheduler.start()

    def init_web_app(self):
        self.web_application = chronograph_webapp
        self.web_application.chronograph = self
        self.server = WSGIServer(get_lisener(self.config['main'].get('web_app')), self.web_application, spawn=100)
        self.server.start()

    def run(self):

        LOGGER.info('Starting node: {}'.format(self.server_name))

        for auction_item in iterview(self.config['main']["couch_url"], self.config['main']['auctions_db'], 'chronograph/start_date'):
            datestamp = (datetime.now(self.timezone) + timedelta(minutes=1)).isoformat()
            # ADD FILTER BY VALUE {start: '2016-09-10T14:36:40.378777+03:00', test: false}
            if datestamp < auction_item['value']['start']:
                worker_cmd_provider = self.mapper(FeedItem(auction_item['value']))
                if not worker_cmd_provider:
                    continue
                self.scheduler.schedule_auction(auction_item['id'],
                                                auction_item['value'],
                                                args=worker_cmd_provider(auction_item['id']))

            if self.scheduler.exit:
                break

        while not self.scheduler.execution_stopped:
            sleep(10)
            LOGGER.info('Wait until execution stopped')


def main():
    parser = argparse.ArgumentParser(description='---- Auctions Chronograph ----')
    parser.add_argument('config', type=str, help='Path to configuration file')
    params = parser.parse_args()
    if os.path.isfile(params.config):
        with open(params.config) as config_file_obj:
            config = load(config_file_obj.read())
        logging.config.dictConfig(config)
        AuctionsChronograph(config).run()


if __name__ == '__main__':
    main()
