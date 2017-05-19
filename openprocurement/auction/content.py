from zope.interface import implements, Interface
from zope.component import adapts, provideUtility
from munch import Munch, munchify
from openprocurement.auction.interfaces import ITenderListingItemData, IResourceListingItemFactory, IAuctionDataBridge, IWorkerCommand
from zope.component.factory import Factory
from time import sleep, mktime, time
import iso8601
from openprocurement.auction.systemd_msgs_ids import (
    DATA_BRIDGE_PLANNING_TENDER_SKIP,
    DATA_BRIDGE_RE_PLANNING_TENDER_ALREADY_PLANNED,
    DATA_BRIDGE_PLANNING_TENDER_ALREADY_PLANNED,
    DATA_BRIDGE_RE_PLANNING_LOT_ALREADY_PLANNED,
    DATA_BRIDGE_PLANNING_LOT_SKIP,
    DATA_BRIDGE_PLANNING_LOT_ALREADY_PLANNED
)
from datetime import datetime, timedelta
MULTILOT_AUCTION_ID = "{0[id]}_{1[id]}"  # {TENDER_ID}_{LOT_ID}

class TenderListingItemData(object):
    adapts(IAuctionDataBridge)
    implements(ITenderListingItemData)

    def __init__(self, auction_data_bridge, item={}):
        self.auction_data_bridge = auction_data_bridge
        self.item = item
        self.auction_documents = {}

    def get_auction_document(self, document_id):
        auction_document = self.auction_documents.get(document_id, None)
        if not auction_document:
            auction_document = self.auction_data_bridge.db.get(self.item['id'])
            self.auction_documents[document_id] = auction_document
        return auction_document

    def iter_planning(self):


        if self.item.status == "active.auction":
            print self.item.status
            import pdb; pdb.set_trace()
            now = datetime.now(self.auction_data_bridge.tz)
            if 'lots' not in self.item and 'auctionPeriod' in self.item and 'startDate' in self.item['auctionPeriod'] \
                    and 'endDate' not in self.item['auctionPeriod']:

                start_date = iso8601.parse_date(self.item['auctionPeriod']['startDate'])
                start_date = start_date.astimezone(self.auction_data_bridge.tz)
                # auctions_start_in_date = self.auction_data_bridge.startDate_view(
                #     self.auction_data_bridge.db,
                #     key=(mktime(start_date.timetuple()) + start_date.microsecond / 1E6) * 1000
                # )

                if now > start_date:
                    self.auction_data_bridge.logger.info("Tender {} start date in past. Skip it for planning".format(self.item['id']),
                                extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING_TENDER_SKIP})
                    raise StopIteration
                auction_document = self.get_auction_document(self.item['id'])
                if auction_document and len(auction_document.get('stages', [])) > 0:
                    if auction_document.get('stages')[0].get('start', None) == start_date:
                        self.auction_data_bridge.logger.info("Tender {} already planned on same date".format(self.item['id']),
                                         extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING_TENDER_ALREADY_PLANNED})
                        raise StopIteration
                # if re_planning and self.item['id'] in self.tenders_ids_list:
                #     self.auction_data_bridge.logger.info("Tender {} already planned while replanning".format(item['id']),
                #                 extra={'MESSAGE_ID': DATA_BRIDGE_RE_PLANNING_TENDER_ALREADY_PLANNED})
                #     continue
                # elif not re_planning and [row.id for row in auctions_start_in_date.rows if row.id == item['id']]:
                #     logger.info("Tender {} already planned on same date".format(item['id']),
                #                 extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING_TENDER_ALREADY_PLANNED})
                #     continue
                print "tender"
                yield (str(self.item['id']), )
            elif 'lots' in self.item:
                for lot in self.item['lots']:
                    if lot["status"] == "active" and 'auctionPeriod' in lot \
                            and 'startDate' in lot['auctionPeriod'] and 'endDate' not in lot['auctionPeriod']:
                        start_date = iso8601.parse_date(lot['auctionPeriod']['startDate'])
                        start_date = start_date.astimezone(self.auction_data_bridge.tz)
                        auction_document_id = MULTILOT_AUCTION_ID.format(self.item, lot)
                        auction_document = self.get_auction_document(self.item['id'])


                        if now > start_date:
                            self.auction_data_bridge.logger.info(
                                "Start date for lot {} in tender {} is in past. Skip it for planning".format(
                                    lot['id'], self.item['id']),
                                extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING_LOT_SKIP}
                            )
                            continue
                        # if re_planning and auction_id in self.tenders_ids_list:
                        #     self.auction_data_bridge.logger.info("Tender {} already planned while replanning".format(auction_id),
                        #                                          extra={'MESSAGE_ID': DATA_BRIDGE_RE_PLANNING_LOT_ALREADY_PLANNED})
                        #     continue
                        # elif not re_planning and [row.id for row in auctions_start_in_date.rows if row.id == auction_id]:
                        #     self.auction_data_bridge.logger.info("Tender {} already planned on same date".format(auction_id),
                        #                                          extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING_LOT_ALREADY_PLANNED})
                        #     continue
                        if auction_document and len(auction_document.get('stages', [])) > 0:
                            if auction_document.get('stages')[0].get('start', None) == start_date:
                                self.auction_data_bridge.logger.info("Tender {} already planned on same date".format(self.item['id']),
                                                 extra={'MESSAGE_ID': DATA_BRIDGE_PLANNING_LOT_ALREADY_PLANNED})
                                continue
                        print "lot"
                        yield (str(self.item["id"]), str(lot["id"]), )

    def ready_to_announce(self):
        pass

    def ready_to_cancel(self):
        pass

# if item['status'] == "active.qualification" and 'lots' in item:
#     for lot in item['lots']:
#         if lot["status"] == "active":
#             is_pre_announce = PreAnnounce_view(self.db)
#             auction_id = MULTILOT_AUCTION_ID.format(item, lot)
#             if [row.id for row in is_pre_announce.rows if row.id == auction_id]:
#                 self.start_auction_worker_cmd('announce', item['id'], lot_id=lot['id'],)
# if item['status'] == "cancelled":
#     future_auctions = endDate_view(
#         self.db, startkey=time() * 1000
#     )
#     if 'lots' in item:
#         for lot in item['lots']:
#             auction_id = MULTILOT_AUCTION_ID.format(item, lot)
#             if auction_id in [i.id for i in future_auctions]:
#                 logger.info('Tender {0} selected for cancellation'.format(item['id']))
#                 self.start_auction_worker_cmd('cancel', item['id'], lot_id=lot['id'])
#     else:
#         if item["id"] in [i.id for i in future_auctions]:
#             logger.info('Tender {0} selected for cancellation'.format(item['id']))
#             self.start_auction_worker_cmd('cancel', item["id"])


class WorkerCommand(object):
    adapts(ITenderListingItemData)
    implements(IWorkerCommand)




def make_tender_listing_item(auction_data_bridge, item):
    return TenderListingItemData(auction_data_bridge, item=munchify(item))


def init_auction():
    make_tender_listing_item_factory = Factory(make_tender_listing_item)
    for procurementMethodType in ['belowThreshold',
                                  'aboveThresholdUA',
                                  'aboveThresholdEU',
                                  'competitiveDialogueEU.stage2',
                                  'competitiveDialogueUA.stage2',
                                  'aboveThresholdUA.defense']:
        provideUtility(make_tender_listing_item_factory, IResourceListingItemFactory, procurementMethodType)


init_auction()
