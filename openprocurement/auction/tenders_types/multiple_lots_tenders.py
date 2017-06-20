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
         'lot': {},
         "worker_class": self.klass
        }
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
                self.auction_document[section][index]["label"]["uk"] = bidders_data[stage['bidder_id']]["name"]
                self.auction_document[section][index]["label"]["ru"] = bidders_data[stage['bidder_id']]["name"]
                self.auction_document[section][index]["label"]["en"] = bidders_data[stage['bidder_id']]["name"]
    self.auction_document["current_stage"] = (len(self.auction_document["stages"]) - 1)

    return None
