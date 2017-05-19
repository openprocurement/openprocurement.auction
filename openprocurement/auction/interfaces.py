from zope.interface import Interface, Attribute
from zope.component.interfaces import IFactory

class IAuctionDataBridge(Interface):
    pass

class IResourceListingItemData(Interface):
    pass

class IResourceAuctionData(Interface):
    pass

class IWorkerCommand(Interface):
    pass

class IResourceListingItemFactory(IFactory):
    pass

########################################


class ITenderListingItemData(IResourceListingItemData):
    pass