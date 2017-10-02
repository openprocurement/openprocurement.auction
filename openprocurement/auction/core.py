import logging.config
import iso8601

from datetime import datetime
from time import mktime, time
from gevent.subprocess import check_call
from pkg_resources import iter_entry_points

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
from openprocurement.auction.utils import do_until_success, \
    prepare_auction_worker_cmd
from openprocurement.auction.auctions_server import auctions_server
from openprocurement.auction.components import AuctionComponents
from openprocurement.auction.predicates import ProcurementMethodType
from openprocurement.auction.interfaces import IAuctionsManager,\
    IAuctionsChronograph, IAuctionDatabridge, IAuctionsServer


SIMPLE_AUCTION_TYPE = 0
SINGLE_LOT_AUCTION_TYPE = 1
MULTILOT_AUCTION_ID = "{0[id]}_{1[id]}"  # {TENDER_ID}_{LOT_ID}
LOGGER = logging.getLogger('Openprocurement Auction')
PKG_NAMESPACE = "openprocurement.auction.auctions"


from openprocurement.auction.worker.auction import LOGGER

components = AuctionComponents()
components.add_predicate('procurementMethodType', ProcurementMethodType)
components.registerUtility(auctions_server, IAuctionsServer)


class AuctionManager(object):
    def __init__(self, for_):
        self.for_ = for_
        self.plugins = self.for_.config.get('main', {}).get('plugins') or []
        for entry_point in iter_entry_points(PKG_NAMESPACE):
            type_ = entry_point.name
            if type_ in self.plugins or type_ == 'default':
                plugin = entry_point.load()
                plugin(components)

    def __repr__(self):
        return "<Auctions mapper for: {}>".format(self.for_)

    __str__ = __repr__

    def __call__(self, raw_data):
        auction_iface = components.match(raw_data)
        if not auction_iface:
            return
        return components.queryMultiAdapter(
            (self.for_, raw_data),
            auction_iface
        )


@components.adapter(provides=IAuctionsManager, adapts=IAuctionDatabridge)
class DatabridgeManager(AuctionManager):
    """"""


@components.adapter(provides=IAuctionsManager, adapts=IAuctionsChronograph)
class ChronographManager(AuctionManager):
    """"""


class RunDispatcher(object):
    """"""
    def __init__(self, chronograph, item):
        self.chronograph = chronograph
        self.item = item

    def __repr__(self):
        return "<Auction runner: {}>".format(
            self.item.get('procurementMethodType', 'default') or 'default'
        )

    __str__ = __repr__

    def __call__(self, document_id):
        if "_" in document_id:
            tender_id, lot_id = document_id.split("_")
        else:
            tender_id = document_id
            lot_id = None
        with_api_version = self.item['api_version']
        params = prepare_auction_worker_cmd(
            self.chronograph,
            tender_id,
            'run',
            self.item,
            lot_id=lot_id,
            with_api_version=with_api_version
        )
        if self.item['mode'] == 'test':
            params += ['--auction_info_from_db', 'true']
        return params


class Planning(object):

    def __init__(self, bridge, item):
        self.bridge = bridge
        self.item = item

    def next(self):
        return self

    def __iter__(self):
        status = self.item.get('status', None)
        if status == "active.auction":
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
                # TODO: Find out about the value of field tenders_ids_list
                # TODO: It is not initialized but used.
                if self.bridge.re_planning and self.item['id'] in self.tenders_ids_list:
                    LOGGER.info("Tender {} already planned while replanning".format(self.item['id']),
                                extra={'MESSAGE_ID': DATA_BRIDGE_RE_PLANNING_TENDER_ALREADY_PLANNED})
                    raise StopIteration
                if not self.bridge.re_planning and [row.id for row in auctions_start_in_date.rows if row.id == self.item['id']]:
                    LOGGER.info("Tender {} already planned on the same date".format(self.item['id']),
                                extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING_TENDER_ALREADY_PLANNED})
                    raise StopIteration
                yield ("planning", str(self.item['id']), "")
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
                        yield ("planning", str(self.item["id"]), str(lot["id"]))
        if status == "active.qualification" and 'lots' in self.item:
            for lot in self.item['lots']:
                if lot["status"] == "active":
                    is_pre_announce = PreAnnounce_view(self.bridge.db)
                    auction_id = MULTILOT_AUCTION_ID.format(self.item, lot)
                    if [row.id for row in is_pre_announce.rows if row.id == auction_id]:
                        yield ('announce', self.item['id'], lot['id'])
            raise StopIteration
        if status == "cancelled":
            future_auctions = endDate_view(
                self.bridge.db, startkey=time() * 1000
            )
            if 'lots' in self.item:
                for lot in self.item['lots']:
                    auction_id = MULTILOT_AUCTION_ID.format(self.item, lot)
                    if auction_id in [i.id for i in future_auctions]:
                        LOGGER.info('Tender {0} selected for cancellation'.format(self.item['id']))
                        yield ('cancel', self.item['id'], lot['id'])
                raise StopIteration
            else:
                if self.item["id"] in [i.id for i in future_auctions]:
                    LOGGER.info('Tender {0} selected for cancellation'.format(self.item['id']))
                    yield ('cancel', self.item['id'], "")
                raise StopIteration
        raise StopIteration

    def __repr__(self):
        return "<Auction planning: {}>".format(self.item.get('procurementMethodType'))

    __str__ = __repr__

    def __call__(self, cmd, tender_id, with_api_version=None, lot_id=None):
        params = prepare_auction_worker_cmd(
            self.bridge,
            tender_id,
            cmd,
            self.item,
            lot_id=lot_id,
            with_api_version=with_api_version
        )

        result = do_until_success(
            check_call,
            args=(params,),
        )

        LOGGER.info("Auction command {} result: {}".format(params[1], result))
