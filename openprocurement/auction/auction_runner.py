import logging
import logging.config
import iso8601
from datetime import datetime
from time import mktime, time
from gevent.subprocess import check_call
from zope.interface import implementer

from openprocurement.auction.systemd_msgs_ids import (
    DATA_BRIDGE_PLANNING_TENDER_SKIP,
    DATA_BRIDGE_PLANNING_TENDER_ALREADY_PLANNED,
    DATA_BRIDGE_PLANNING_LOT_SKIP,
    DATA_BRIDGE_PLANNING_LOT_ALREADY_PLANNED,
    DATA_BRIDGE_RE_PLANNING_TENDER_ALREADY_PLANNED,
    DATA_BRIDGE_RE_PLANNING_LOT_ALREADY_PLANNED,
)
from openprocurement.auction.design import endDate_view, startDate_view,\
        PreAnnounce_view
from openprocurement.auction.utils import do_until_success
from openprocurement.auction.interfaces import IAuctionsRunner


SIMPLE_AUCTION_TYPE = 0
SINGLE_LOT_AUCTION_TYPE = 1
MULTILOT_AUCTION_ID = "{0[id]}_{1[id]}"  # {TENDER_ID}_{LOT_ID}
LOGGER = logging.getLogger(__name__)


@implementer(IAuctionsRunner)
class MultilotAuctionRunner(object):

    worker = 'multilot'

    def __init__(self, bridge, item):
        self.item = item
        self.bridge = bridge
        # DEBUG:
        # print "Multilot auction runner"

    def __repr__(self):
        return "<Multilot: {}>".format(self.item.get('procurementMethodType'))

    __str__ = __repr__

    def next(self):
        return self

    def __iter__(self):
        if self.item['status'] == "active.auction":
            for lot in self.item['lots']:
                if lot["status"] == "active" and 'auctionPeriod' in lot \
                        and 'startDate' in lot['auctionPeriod'] and 'endDate' not in lot['auctionPeriod']:
                    start_date = iso8601.parse_date(lot['auctionPeriod']['startDate'])
                    start_date = start_date.astimezone(self.bridge.tz)
                    auctions_start_in_date = startDate_view(
                        self.bridge.db,
                        key=(mktime(start_date.timetuple()) + start_date.microsecond / 1E6) * 1000
                    )
                    if datetime.now(self.bridge.tz) > start_date:
                        LOGGER.info(
                            "Start date for lot {} in tender {} is in past. Skip it for planning".format(
                                lot['id'], self.item['id']),
                            extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING_LOT_SKIP}
                        )
                        raise StopIteration
                    auction_id = MULTILOT_AUCTION_ID.format(self.item, lot)
                    if self.bridge.re_planning and auction_id in self.tenders_ids_list:
                        LOGGER.info("Tender {} already planned while replanning".format(auction_id),
                                    extra={'MESSAGE_ID': DATA_BRIDGE_RE_PLANNING_LOT_ALREADY_PLANNED})
                        raise StopIteration
                    elif not self.bridge.re_planning and [row.id for row in auctions_start_in_date.rows if row.id == auction_id]:
                        LOGGER.info("Tender {} already planned on same date".format(auction_id),
                                    extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING_LOT_ALREADY_PLANNED})
                        raise StopIteration
                    yield (str(self.item["id"]), str(lot["id"]), )
        if self.item['status'] == "active.qualification" and 'lots' in self.item:
            for lot in self.item['lots']:
                if lot["status"] == "active":
                    is_pre_announce = PreAnnounce_view(self.bridge.db)
                    auction_id = MULTILOT_AUCTION_ID.format(self.item, lot)
                    if [row.id for row in is_pre_announce.rows if row.id == auction_id]:
                        # TODO:
                        yield (self.item['id'], lot['id'])
                        #self.start_auction_worker_cmd('announce', self.item['id'], lot_id=lot['id'],)
            raise StopIteration
        if self.item['status'] == "cancelled":
            future_auctions = endDate_view(
                self.bridge.db, startkey=time() * 1000
            )
            for lot in self.item['lots']:
                auction_id = MULTILOT_AUCTION_ID.format(self.item, lot)
                if auction_id in [i.id for i in future_auctions]:
                    LOGGER.info('Tender {0} selected for cancellation'.format(self.item['id']))
                    yield (self.item['id'], lot['id'])
                    # TODO:
                    #self.start_auction_worker_cmd('cancel', self.item['id'], lot_id=lot['id'])
        raise StopIteration

    def run_worker(self, cmd, tender_id, with_api_version=None, lot_id=None):
        # DEBUG ONLY:
        print "Running multilot {} on worker {} tender {}".format(cmd, self.item.get('procurementMethodType'), tender_id)


@implementer(IAuctionsRunner)
class AuctionsRunner(object):

    worker = 'auction'

    def __init__(self, bridge, item):
        self.item = item
        self.bridge = bridge

    def next(self):
        return self

    def __iter__(self):
        if self.item['status'] == "active.auction":
            if 'lots' not in self.item and 'auctionPeriod' in self.item and 'startDate' in self.item['auctionPeriod'] \
                    and 'endDate' not in self.item['auctionPeriod']:

                start_date = iso8601.parse_date(self.item['auctionPeriod']['startDate'])
                start_date = start_date.astimezone(self.bridge.tz)
                auctions_start_in_date = startDate_view(
                    self.bridge.db,
                    key=(mktime(start_date.timetuple()) + start_date.microsecond / 1E6) * 1000
                )
                if datetime.now(self.bridge.tz) > start_date:
                    LOGGER.info("Tender {} start date in past. Skip it for planning".format(self.item['id']),
                                extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING_TENDER_SKIP})
                    raise StopIteration
                if self.bridge.re_planning and self.item['id'] in self.tenders_ids_list:
                    LOGGER.info("Tender {} already planned while replanning".format(self.item['id']),
                                extra={'MESSAGE_ID': DATA_BRIDGE_RE_PLANNING_TENDER_ALREADY_PLANNED})
                    raise StopIteration
                elif not self.bridge.re_planning and [row.id for row in auctions_start_in_date.rows if row.id == self.item['id']]:
                    LOGGER.info("Tender {} already planned on same date".format(self.item['id']),
                                extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING_TENDER_ALREADY_PLANNED})
                    raise StopIteration
                yield (str(self.item['id']), )
            elif 'lots' in self.item:
                for lot in self.item['lots']:
                    if lot["status"] == "active" and 'auctionPeriod' in lot \
                            and 'startDate' in lot['auctionPeriod'] and 'endDate' not in lot['auctionPeriod']:
                        start_date = iso8601.parse_date(lot['auctionPeriod']['startDate'])
                        start_date = start_date.astimezone(self.bridge.tz)
                        auctions_start_in_date = startDate_view(
                            self.bridge.db,
                            key=(mktime(start_date.timetuple()) + start_date.microsecond / 1E6) * 1000
                        )
                        if datetime.now(self.bridge.tz) > start_date:
                            LOGGER.info(
                                "Start date for lot {} in tender {} is in past. Skip it for planning".format(
                                    lot['id'], self.item['id']),
                                extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING_LOT_SKIP}
                            )
                            raise StopIteration
                        auction_id = MULTILOT_AUCTION_ID.format(self.item, lot)
                        if self.bridge.re_planning and auction_id in self.tenders_ids_list:
                            LOGGER.info("Tender {} already planned while replanning".format(auction_id),
                                        extra={'MESSAGE_ID': DATA_BRIDGE_RE_PLANNING_LOT_ALREADY_PLANNED})
                            raise StopIteration
                        elif not self.bridge.re_planning and [row.id for row in auctions_start_in_date.rows if row.id == auction_id]:
                            LOGGER.info("Tender {} already planned on same date".format(auction_id),
                                        extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING_LOT_ALREADY_PLANNED})
                            raise StopIteration
                        yield (str(self.item["id"]), str(lot["id"]), )
        if self.item['status'] == "active.qualification" and 'lots' in self.item:
            for lot in self.item['lots']:
                if lot["status"] == "active":
                    is_pre_announce = PreAnnounce_view(self.bridge.db)
                    auction_id = MULTILOT_AUCTION_ID.format(self.item, lot)
                    if [row.id for row in is_pre_announce.rows if row.id == auction_id]:
                        # TODO:
                        yield (self.item['id'], lot['id'])
                        #self.start_auction_worker_cmd('announce', self.item['id'], lot_id=lot['id'],)
            raise StopIteration
        if self.item['status'] == "cancelled":
            future_auctions = endDate_view(
                self.bridge.db, startkey=time() * 1000
            )
            if 'lots' in self.item:
                for lot in self.item['lots']:
                    auction_id = MULTILOT_AUCTION_ID.format(self.item, lot)
                    if auction_id in [i.id for i in future_auctions]:
                        LOGGER.info('Tender {0} selected for cancellation'.format(self.item['id']))
                        yield (self.item['id'], lot['id'])
                        # TODO:
                        #self.start_auction_worker_cmd('cancel', self.item['id'], lot_id=lot['id'])
                raise StopIteration
            else:
                if self.item["id"] in [i.id for i in future_auctions]:
                    LOGGER.info('Tender {0} selected for cancellation'.format(self.item['id']))
                    # TODO:
                    yield (self.item['id'],)
                    #self.start_auction_worker_cmd('cancel', self.item["id"])
                raise StopIteration
        raise StopIteration

   def __repr__(self):
        return "<Simple: {}>".format(self.item.get('procurementMethodType'))
    
    __str__ = __repr__

    def run_worker(self, cmd, tender_id, with_api_version=None, lot_id=None):
        # DEBUG ONLY:
        print "Running simple {} on worker {} tender {}".format(cmd, self.item.get('procurementMethodType'), tender_id)
        # params = [self.config_get('auction_worker'),
        #           cmd, tender_id,
        #           self.config_get('auction_worker_config')]
        # if lot_id:
        #     params += ['--lot', lot_id]
        #
        # if with_api_version:
        #     params += ['--with_api_version', with_api_version]
        #
        # result = do_until_success(
        #     check_call,
        #     args=(params,),
        # )
        #
        # LOGGER.info("Auction command {} result: {}".format(params[1], result))
