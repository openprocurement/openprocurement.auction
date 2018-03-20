import logging
import copy
import sys
from ..templates import prepare_service_stage
from ..utils import calculate_hash
from ..utils import (
    get_tender_data,
    get_latest_bid_for_bidder,
    make_request
)
from ..systemd_msgs_ids import(
    AUCTION_WORKER_API_AUCTION_CANCEL,
    AUCTION_WORKER_API_AUCTION_NOT_EXIST,
    AUCTION_WORKER_SERVICE_NUMBER_OF_BIDS,
    AUCTION_WORKER_API_APPROVED_DATA,
    AUCTION_WORKER_SET_AUCTION_URLS
)
from barbecue import calculate_coeficient, cooking

MULTILINGUAL_FIELDS = ['title', 'description']
ADDITIONAL_LANGUAGES = ['ru', 'en']
ROUNDS = 3
logger = logging.getLogger('Auction Worker')


def get_auction_info(self, prepare=False):
    if not self.debug:
        if prepare:
            self._auction_data = get_tender_data(
                self.tender_url,
                request_id=self.request_id,
                session=self.session
            )
        else:
            self._auction_data = {'data': {}}
        auction_data = get_tender_data(
            self.tender_url + '/auction',
            user=self.worker_defaults['TENDERS_API_TOKEN'],
            request_id=self.request_id,
            session=self.session
        )
        if auction_data:
            self._auction_data['data'].update(auction_data['data'])
            del auction_data
        else:
            self.get_auction_document()
            if self.auction_document:
                self.auction_document['current_stage'] = -100
                self.save_auction_document()
                logger.warning('Cancel auction: {}'.format(
                    self.auction_doc_id
                ), extra={'JOURNAL_REQUEST_ID': self.request_id,
                          'MESSAGE_ID': AUCTION_WORKER_API_AUCTION_CANCEL})
            else:
                logger.error('Auction {} not exists'.format(
                    self.auction_doc_id
                ), extra={'JOURNAL_REQUEST_ID': self.request_id,
                          'MESSAGE_ID': AUCTION_WORKER_API_AUCTION_NOT_EXIST})
            self._end_auction_event.set()
            sys.exit(1)
    self._lot_data = dict({item['id']: item for item in self._auction_data['data']['lots']}[self.lot_id])
    self._lot_data['items'] = [item for item in self._auction_data['data'].get('items', [])
                               if item.get('relatedLot') == self.lot_id]
    self._lot_data['features'] = [
        item for item in self._auction_data['data'].get('features', [])
        if item['featureOf'] == 'tenderer' \
        or item['featureOf'] == 'lot' and item['relatedItem'] == self.lot_id \
        or item['featureOf'] == 'item' and item['relatedItem'] in [i['id'] for i in self._lot_data['items']]
    ]
    self.startDate = self.convert_datetime(
        self._lot_data['auctionPeriod']['startDate']
    )
    self.bidders_features = None
    self.features = self._lot_data.get('features', None)
    if not prepare:
        codes = [i['code'] for i in self._lot_data['features']]
        self.bidders_data = []
        for bid_index, bid in enumerate(self._auction_data['data']['bids']):
            if bid.get('status', 'active') == 'active':
                for lot_index, lot_bid in enumerate(bid['lotValues']):
                    if lot_bid['relatedLot'] == self.lot_id and lot_bid.get('status', 'active') == 'active':
                        bid_data = {
                            'id': bid['id'],
                            'date': lot_bid['date'],
                            'value': lot_bid['value']
                        }
                        if 'parameters' in bid:
                            bid_data['parameters'] = [i for i in bid['parameters']
                                                      if i['code'] in codes]
                        self.bidders_data.append(bid_data)
        self.bidders_count = len(self.bidders_data)
        logger.info('Bidders count: {}'.format(self.bidders_count),
                    extra={'JOURNAL_REQUEST_ID': self.request_id,
                           'MESSAGE_ID': AUCTION_WORKER_SERVICE_NUMBER_OF_BIDS})
        self.rounds_stages = []
        for stage in range((self.bidders_count + 1) * ROUNDS + 1):
            if (stage + self.bidders_count) % (self.bidders_count + 1) == 0:
                self.rounds_stages.append(stage)
        self.mapping = {}
        if self._lot_data.get('features', None):
            self.bidders_features = {}
            self.bidders_coeficient = {}
            self.features = self._lot_data['features']
            for bid in self.bidders_data:
                self.bidders_features[bid['id']] = bid['parameters']
                self.bidders_coeficient[bid['id']] = calculate_coeficient(self.features, bid['parameters'])
        else:
            self.bidders_features = None
            self.features = None

        for index, uid in enumerate(self.bidders_data):
            self.mapping[self.bidders_data[index]['id']] = str(index + 1)


def prepare_auction_document(self):
    self.auction_document.update(
        {'_id': self.auction_doc_id,
         'stages': [],
         'tenderID': self._auction_data['data'].get('tenderID', ''),
         'TENDERS_API_VERSION': self.worker_defaults['TENDERS_API_VERSION'],
         'initial_bids': [],
         'current_stage': -1,
         'results': [],
         'minimalStep': self._lot_data.get('minimalStep', {}),
         'procuringEntity': self._auction_data['data'].get('procuringEntity', {}),
         'items': self._lot_data.get('items', []),
         'value': self._lot_data.get('value', {}),
         'lot': {}}
    )
    self.auction_document['auction_type'] = 'meat' if self.features else 'default'

    for key in MULTILINGUAL_FIELDS:
        for lang in ADDITIONAL_LANGUAGES:
            lang_key = '{}_{}'.format(key, lang)
            if lang_key in self._auction_data['data']:
                self.auction_document[lang_key] = self._auction_data['data'][lang_key]
            if lang_key in self._lot_data:
                self.auction_document['lot'][lang_key] = self._lot_data[lang_key]
        self.auction_document[key] = self._auction_data['data'].get(key, '')
        self.auction_document['lot'][key] = self._lot_data.get(key, '')

    self.auction_document['stages'].append(
        prepare_service_stage(
            start=self.startDate.isoformat(),
            type="pause"
        )
    )
    return self.auction_document


def prepare_auction_and_participation_urls(self):
    auction_url = self.worker_defaults['AUCTIONS_URL'].format(
        auction_id=self.auction_doc_id
    )
    patch_data = {'data': {'lots': list(self._auction_data['data']['lots']),
                           'bids': list(self._auction_data['data']['bids'])}}
    for index, lot in enumerate(self._auction_data['data']['lots']):
        if lot['id'] == self.lot_id:
            patch_data['data']['lots'][index]['auctionUrl'] = auction_url
            break

    for bid_index, bid in enumerate(self._auction_data['data']['bids']):
        if bid.get('status', 'active') == 'active':
            for lot_index, lot_bid in enumerate(bid['lotValues']):
                if lot_bid['relatedLot'] == self.lot_id and lot_bid.get('status', 'active') == 'active':
                    participation_url = self.worker_defaults['AUCTIONS_URL'].format(
                        auction_id=self.auction_doc_id
                    )
                    participation_url += '/login?bidder_id={}&hash={}'.format(
                        bid['id'],
                        calculate_hash(bid['id'], self.worker_defaults['HASH_SECRET'])
                    )
                    patch_data['data']['bids'][bid_index]['lotValues'][lot_index]['participationUrl'] = participation_url
                    break
    logger.info("Set auction and participation urls for tender {}".format(self.tender_id),
                extra={"JOURNAL_REQUEST_ID": self.request_id,
                       "MESSAGE_ID": AUCTION_WORKER_SET_AUCTION_URLS})
    logger.info(repr(patch_data))
    make_request(self.tender_url + '/auction/{}'.format(self.lot_id), patch_data,
                 user=self.worker_defaults["TENDERS_API_TOKEN"],
                 request_id=self.request_id, session=self.session)
    return patch_data


def post_results_data(self, with_auctions_results=True):
    patch_data = {'data': {'bids': list(self._auction_data['data']['bids'])}}
    if with_auctions_results:
        for bid_index, bid in enumerate(self._auction_data['data']['bids']):
            if bid.get('status', 'active') == 'active':
                for lot_index, lot_bid in enumerate(bid['lotValues']):
                    if lot_bid['relatedLot'] == self.lot_id and lot_bid.get('status', 'active') == 'active':
                        auction_bid_info = get_latest_bid_for_bidder(self.auction_document["results"], bid["id"])
                        patch_data['data']['bids'][bid_index]['lotValues'][lot_index]["value"]["amount"] = auction_bid_info["amount"]
                        patch_data['data']['bids'][bid_index]['lotValues'][lot_index]["date"] = auction_bid_info["time"]
                        break

    logger.info(
        "Approved data: {}".format(patch_data),
        extra={"JOURNAL_REQUEST_ID": self.request_id,
               "MESSAGE_ID": AUCTION_WORKER_API_APPROVED_DATA}
    )
    results = make_request(
        self.tender_url + '/auction/{}'.format(self.lot_id), data=patch_data,
        user=self.worker_defaults["TENDERS_API_TOKEN"],
        method='post',
        request_id=self.request_id, session=self.session
    )
    return results


def announce_results_data(self, results=None):
    if not results:
        results = get_tender_data(
            self.tender_url,
            user=self.worker_defaults["TENDERS_API_TOKEN"],
            request_id=self.request_id,
            session=self.session
        )

    bidders_data = {}

    for bid_index, bid in enumerate(results['data']['bids']):
        if bid.get('status', 'active') == 'active':
            for lot_index, lot_bid in enumerate(bid['lotValues']):
                if lot_bid['relatedLot'] == self.lot_id and lot_bid.get('status', 'active') == 'active':
                    bid_data = {
                        'id': bid['id'],
                        'name': bid['tenderers'][0]['name']
                    }
                    bidders_data[bid['id']] = bid_data

    for section in ['initial_bids', 'stages', 'results']:
        for index, stage in enumerate(self.auction_document[section]):
            if 'bidder_id' in stage and stage['bidder_id'] in bidders_data:
                self.auction_document[section][index]["label"]["ro"] = bidders_data[stage['bidder_id']]["name"]
                self.auction_document[section][index]["label"]["ru"] = bidders_data[stage['bidder_id']]["name"]
                self.auction_document[section][index]["label"]["en"] = bidders_data[stage['bidder_id']]["name"]
    self.auction_document["current_stage"] = (len(self.auction_document["stages"]) - 1)

    return None
