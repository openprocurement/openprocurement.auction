import logging
from zope import interface
from zope.interface import registry, implementedBy
from walkabout import PredicateDomain, PredicateMismatch
from pkg_resources import iter_entry_points

from openprocurement.auction.predicates import ProcurementMethodType
from openprocurement.auction.interfaces import IComponents, IAuctionType,\
    IFeedItem, IAuctionDatabridge, IAuctionsMapper, IAuctionsRunner, IAuctionWorker, IAuctionsChronograph, IDBData


PKG_NAMESPACE = "openprocurement.auction.auctions"
LOGGER = logging.getLogger(__name__)


@interface.implementer(IComponents)
class AuctionComponents(registry.Components):

    def __init__(self, *args, **kw):
        super(AuctionComponents, self).__init__(*args, **kw)
        self._dispatch = PredicateDomain(IAuctionType, self)

    def add_predicate(self, *args, **kw):
        self._dispatch.add_predicate(*args, **kw)

    def add_auction(self, iface, **preds):
        self._dispatch.add_candidate(iface, IFeedItem, **preds)

    def match(self, inst):
        try:
            return self._dispatch.lookup(inst)
        except PredicateMismatch:
            pass

    def adapter(self, provides, adapts, name=""):
        """ TODO: create decorator for such thinks """

        if not isinstance(adapts, (tuple, list)):
            adapts = (adapts,)

        def wrapped(wrapper):

            self.registerAdapter(
                wrapper,
                adapts,
                provides,
                name=name
            )
            return wrapper

        return wrapped

    def qA(self, obj, iface, name=''):
        return self.queryAdapter(obj, iface, name=name)

    def q(self, iface, name='', default=''):
        """ TODO: query the component by 'iface' """
        return self.queryUtility(iface, name=name, default=default)


components = AuctionComponents()
components.add_predicate('procurementMethodType', ProcurementMethodType)


class AuctionMapper(object):
    def __init__(self, for_):
        self.for_ = for_
        self.plugins = self.for_.config.get('main', {}).get('plugins') or []
        for entry_point in iter_entry_points(PKG_NAMESPACE):
            type_ = entry_point.name
            if type_ in self.plugins or type_ == 'default':
                plugin = entry_point.load()
                plugin(type_)

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


@components.adapter(provides=IAuctionsMapper, adapts=IAuctionDatabridge)
class DatabridgeManager(AuctionMapper):
    """"""


@components.adapter(provides=IAuctionsMapper, adapts=IAuctionsChronograph)
class ChronographManager(AuctionMapper):
    """"""
