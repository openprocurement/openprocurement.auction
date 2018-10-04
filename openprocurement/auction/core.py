# -*- coding: utf-8 -*-
from pkg_resources import iter_entry_points

from openprocurement.auction.utils import prepare_auction_worker_cmd
from openprocurement.auction.auctions_server import auctions_server
from openprocurement.auction.components import AuctionComponents
from openprocurement.auction.predicates import ProcurementMethodType
from openprocurement.auction.interfaces import (
    IAuctionsManager, IAuctionsChronograph,
    IAuctionDatabridge, IAuctionsServer
)


SIMPLE_AUCTION_TYPE = 0
SINGLE_LOT_AUCTION_TYPE = 1
MULTILOT_AUCTION_ID = "{0[id]}_{1[id]}"  # {TENDER_ID}_{LOT_ID}
PKG_NAMESPACE = "openprocurement.auction.components"


components = AuctionComponents()
components.add_predicate('procurementMethodType', ProcurementMethodType)
components.registerUtility(auctions_server, IAuctionsServer)


class AuctionManager(object):

    def __init__(self, for_):
        self.for_ = for_
        self.plugins = self.for_.config.get('main', {}).get('plugins') or []
        self.pmt_configurator = {}
        for entry_point in iter_entry_points(PKG_NAMESPACE):
            type_ = entry_point.name
            if type_ in self.plugins or type_ == 'default':
                plugin = entry_point.load()
                pmts = self.plugins.get(type_, {}).get('procurement_method_types', [])
                plugin(components, pmts)
                for pmt in pmts:
                    self.pmt_configurator[pmt] = type_

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
            "run",
            self.item,
            lot_id=lot_id,
            with_api_version=with_api_version
        )
        if self.item['mode'] == 'test':
            params += ['--auction_info_from_db', 'true']
        return params
