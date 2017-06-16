from zope import interface
from zope.interface import registry, implementedBy
from openprocurement.auction.interfaces import IComponents


@interface.implementer(IComponents)
class AuctionComponents(Components):

    def getImplementer(self, obj, iface, default):
        if not iface.providedBy(obj):
            return self.queryAdapter(obj, iface, default=default)
        return obj

    def adapter(self, provides, adapts, name=""):
        """ TODO: create decorator for such thinks """
        
        if not isinstance(adapts, (tuple, list)):
            adapts = (adapts,)

        def wrapped(wrapper):
            
            self.registerAdapter(
                wrapper,
                provides,
                adapts,
                name=name
            )
            return wrapper

        return wrapped
        
    def component(self, name=""):
        """ TODO: use wraps decorator??
        """
        
        def wrapped(wrapped):
            try:
                iface = list(implementedBy(wrapped))[0]
            except IndexError:
                raise ValueError("{} should be marked as interface".format(wrapped.__name__))
            
            class Wrapped(wrapped):
                __doc__ = wrapped.__doc__
                __name__ = wrapped.__name__
                def __new__(cls, *args, **kw):
                    ob = sef.queryUtility(iface, name=name)
                    if not ob:
                        ob = super(Wrapped, cls).__new__(*ags, **kw)
                        self.regiterUtility(ob, iface, name=name)
                    return ob
            return Wrapped
        return wrapped

    def qA(self, obj, iface, name=''):
        return self.queryAdapter(obj, iface, name=name)
        
    def q(self, iface, name='', default=''):
        """ TODO: query the component by 'iface' """    
        return self.queryUtility(iface, name=name, default=default)

        
components = AuctionComponents()

