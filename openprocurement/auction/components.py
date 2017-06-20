import logging
from zope import interface
from zope.interface import registry, implementedBy
from walkabout import PredicateDomain, PredicateMismatch
from pkg_resources import iter_entry_points

from openprocurement.auction.interfaces import IComponents, IAuctionType,\
    IFeedItem, IAuctionDatabridge, IAuctionsMapper, IAuctionsRunner, IAuctionWorker


PKG_NAMESPACE = "openprocurement.auction.plugins"
LOGGER = logging.getLogger(__name__)


@interface.implementer(IComponents)
class AuctionComponents(registry.Components):

    def __init__(self, *args, **kw):
        super(AuctionComponents, self).__init__(*args, **kw)
        self._dispatch = PredicateDomain(IAuctionType, self)

    def add_predicate(self, *args, **kw):
        self._dispatch.add_predicate(*args, **kw)

    def contains_pred(self, name):
        return name in self._dispatch.predicates.sorter.names

    def add_auction(self, auction_iface, **preds):
        self._dispatch.add_candidate(
            auction_iface, IFeedItem, **preds
        )

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


@components.adapter(provides=IAuctionsMapper, adapts=IAuctionDatabridge)
class AuctionMapper(object):

    def __init__(self, databridge):
        self.databridge = databridge
        self.plugins = self.databridge.config_get('plugins') or []

        # TODO: check me
        for entry_point in iter_entry_points(PKG_NAMESPACE):
            plugin = entry_point.load()
            plugin(components)

    def __repr__(self):
        return "<Auctions mapper {}>".format(self.plugins)

    __str__ = __repr__

    def __call__(self, feed):
        auction_iface = components.match(feed)
        if not auction_iface:
            return 
        return components.queryMultiAdapter(
            (self.databridge, feed),
            auction_iface
        )
