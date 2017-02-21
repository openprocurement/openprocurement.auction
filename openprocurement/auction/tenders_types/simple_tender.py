
import logging

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
from barbecue import calculate_coeficient

MULTILINGUAL_FIELDS = ["title", "description"]
ADDITIONAL_LANGUAGES = ["ru", "en"]
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
            user=self.worker_defaults["resource_api_token"],
            request_id=self.request_id,
            session=self.session
        )
        if auction_data:
            self._auction_data['data'].update(auction_data['data'])
            self.startDate = self.convert_datetime(self._auction_data['data']['auctionPeriod']['startDate'])
            del auction_data
        else:
            self.get_auction_document()
            if self.auction_document:
                self.auction_document["current_stage"] = -100
                self.save_auction_document()
                logger.warning("Cancel auction: {}".format(
                    self.auction_doc_id
                ), extra={"JOURNAL_REQUEST_ID": self.request_id,
                          "MESSAGE_ID": AUCTION_WORKER_API_AUCTION_CANCEL})
            else:
                logger.error("Auction {} not exists".format(
                    self.auction_doc_id
                ), extra={"JOURNAL_REQUEST_ID": self.request_id,
                          "MESSAGE_ID": AUCTION_WORKER_API_AUCTION_NOT_EXIST})
            self._end_auction_event.set()
            sys.exit(1)
    self.bidders = [bid["id"]
                    for bid in self._auction_data["data"]["bids"]
                    if bid.get('status', 'active') == 'active']
    self.bidders_count = len(self.bidders)
    logger.info("Bidders count: {}".format(self.bidders_count),
                extra={"JOURNAL_REQUEST_ID": self.request_id,
                       "MESSAGE_ID": AUCTION_WORKER_SERVICE_NUMBER_OF_BIDS})
    self.rounds_stages = []
    for stage in range((self.bidders_count + 1) * ROUNDS + 1):
        if (stage + self.bidders_count) % (self.bidders_count + 1) == 0:
            self.rounds_stages.append(stage)
    self.mapping = {}
    self.startDate = self.convert_datetime(
        self._auction_data['data']['auctionPeriod']['startDate']
    )
    if "features" in self._auction_data["data"]:
        self.features = self._auction_data["data"]["features"]

    if not prepare:
        self.bidders_data = []
        if self.features:
            self.bidders_features = {}
            self.bidders_coeficient = {}
            self.features = self._auction_data["data"]["features"]
            for bid in self._auction_data["data"]["bids"]:
                if bid.get('status', 'active') == 'active':
                    self.bidders_features[bid["id"]] = bid["parameters"]
                    self.bidders_coeficient[bid["id"]] = calculate_coeficient(self.features, bid["parameters"])
        else:
            self.bidders_features = None
            self.features = None

        for bid in self._auction_data['data']['bids']:
            if bid.get('status', 'active') == 'active':
                self.bidders_data.append({
                    'id': bid['id'],
                    'date': bid['date'],
                    'value': bid['value'],
                    'owner': bid.get('owner', '')
                })
                if self.features:
                    self.bidders_features[bid["id"]] = bid["parameters"]
                    self.bidders_coeficient[bid["id"]] = calculate_coeficient(self.features, bid["parameters"])
        self.bidders_count = len(self.bidders_data)

        for index, uid in enumerate(self.bidders_data):
            self.mapping[self.bidders_data[index]['id']] = str(index + 1)


def prepare_auction_document(self):
    self.auction_document.update(
        {"_id": self.auction_doc_id,
         "stages": [],
         "auctionID": self._auction_data["data"].get("auctionID", ""),
         "TENDERS_API_VERSION": self.worker_defaults["resource_api_version"],
         "initial_bids": [],
         "current_stage": -1,
         "results": [],
         "minimalStep": self._auction_data["data"].get("minimalStep", {}),
         "procuringEntity": self._auction_data["data"].get("procuringEntity", {}),
         "items": self._auction_data["data"].get("items", []),
         "value": self._auction_data["data"].get("value", {})}
    )
    if self.features:
        self.auction_document["auction_type"] = "meat"
    else:
        self.auction_document["auction_type"] = "default"

    for key in MULTILINGUAL_FIELDS:
        for lang in ADDITIONAL_LANGUAGES:
            lang_key = "{}_{}".format(key, lang)
            if lang_key in self._auction_data["data"]:
                self.auction_document[lang_key] = self._auction_data["data"][lang_key]
        self.auction_document[key] = self._auction_data["data"].get(key, "")

    self.auction_document['stages'].append(
        prepare_service_stage(
            start=self.startDate.isoformat(),
            type="pause"
        )
    )

    return self.auction_document


def prepare_auction_and_participation_urls(self):
    auction_url = self.worker_defaults["AUCTIONS_URL"].format(
        auction_id=self.tender_id
    )
    patch_data = {"data": {"auctionUrl": auction_url, "bids": []}}
    for bid in self._auction_data["data"]["bids"]:
        if bid.get('status', 'active') == 'active':
            participation_url = self.worker_defaults["AUCTIONS_URL"].format(
                auction_id=self.auction_doc_id
            )
            participation_url += '/login?bidder_id={}&hash={}'.format(
                bid["id"],
                calculate_hash(bid["id"], self.worker_defaults["HASH_SECRET"])
            )
            patch_data['data']['bids'].append(
                {"participationUrl": participation_url,
                 "id": bid["id"]}
            )
        else:
            patch_data['data']['bids'].append({"id": bid["id"]})
    logger.info("Set auction and participation urls for tender {}".format(self.tender_id),
                extra={"JOURNAL_REQUEST_ID": self.request_id,
                       "MESSAGE_ID": AUCTION_WORKER_SET_AUCTION_URLS})
    logger.info(repr(patch_data))
    make_request(self.tender_url + '/auction', patch_data,
                 user=self.worker_defaults["resource_api_token"],
                 request_id=self.request_id, session=self.session)


def post_results_data(self):
    all_bids = self.auction_document["results"]

    for index, bid_info in enumerate(self._auction_data["data"]["bids"]):
        if bid_info.get('status', 'active') == 'active':
            auction_bid_info = get_latest_bid_for_bidder(all_bids, bid_info["id"])
            self._auction_data["data"]["bids"][index]["value"]["amount"] = auction_bid_info["amount"]
            self._auction_data["data"]["bids"][index]["date"] = auction_bid_info["time"]

    data = {'data': {'bids': self._auction_data["data"]['bids']}}
    logger.info(
        "Approved data: {}".format(data),
        extra={"JOURNAL_REQUEST_ID": self.request_id,
               "MESSAGE_ID": AUCTION_WORKER_API_APPROVED_DATA}
    )
    return make_request(
        self.tender_url + '/auction', data=data,
        user=self.worker_defaults["resource_api_token"],
        method='post',
        request_id=self.request_id, session=self.session
    )


def announce_results_data(self, results=None):
    if not results:
        results = get_tender_data(
            self.tender_url,
            user=self.worker_defaults["resource_api_token"],
            request_id=self.request_id,
            session=self.session
        )
    bids_information = dict([(bid["id"], bid)
                             for bid in results["data"]["bids"]
                             if bid.get("status", "active") in ("active", "invalid")])
    for section in ['initial_bids', 'stages', 'results']:
        for index, stage in enumerate(self.auction_document[section]):
            if 'bidder_id' in stage and stage['bidder_id'] in bids_information:
                self.auction_document[section][index]["label"]["uk"] = bids_information[stage['bidder_id']]["tenderers"][0]["name"]
                self.auction_document[section][index]["label"]["ru"] = bids_information[stage['bidder_id']]["tenderers"][0]["name"]
                self.auction_document[section][index]["label"]["en"] = bids_information[stage['bidder_id']]["tenderers"][0]["name"]
    self.auction_document["current_stage"] = (len(self.auction_document["stages"]) - 1)
    return bids_information
