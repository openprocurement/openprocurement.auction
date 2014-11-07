import argparse
import logging
# import requests
import iso8601
import couchdb
import json

from copy import deepcopy
from datetime import timedelta, datetime
from pytz import timezone
from gevent.event import Event
from gevent.coros import BoundedSemaphore
from apscheduler.schedulers.gevent import GeventScheduler
from .server import run_server
from .utils import (
    filter_by_bidder_id, sorting_by_amount,
    get_latest_bid_for_bidder,
    sorting_by_time
)
from string import Template
SCHEDULER = GeventScheduler()
SCHEDULER.timezone = timezone('Europe/Kiev')

logging.basicConfig(level=logging.INFO,
                    format='%(levelname)s[%(asctime)s]: %(message)s')

INITIAL_BIDS_TEMPLATE = Template('''{
    "bidder_id": "$bidder_id",
    "time": "$time",
    "label": {"en": "$bidder_name"},
    "amount": $amount
}''')

PRELINARY_BIDS_TEMPLATE = Template('''{
    "type": "preliminary_bids",
    "start": "$start_time",
    "label": {"en": "Preliminary bids"}
}''')

PAUSE_TEMPLATE = Template('''{
    "type": "pause",
    "start": "$start_time",
    "label": {"en": "Pause"}
}''')

BIDS_TEMPLATE = Template('''{
    "type": "bids",
    "bidder_id": "$bidder_id",
    "start": "$start_time",
    "label": {"en": "$bidder_name"},
    "amount": $amount,
    "time": "$time"
}''')

ANNOUNCEMENT_TEMPLATE = Template('''{
    "type": "announcement",
    "start": "$start_time",
    "label": {"en": "Announcement"}
}''')

ROUNDS = 3
PAUSE_SECONDS = 120
BIDS_SECONDS = 120
PRELIMITARY_BIDS_SECONDS = 300
ANNOUNCEMENT_SECONDS = 150


class Auction(object):
    """docstring for Auction"""
    def __init__(self, auction_doc_id, host='', port=8888,
                 database_url='http://localhost:9000/auction'):
        super(Auction, self).__init__()
        self.host = host
        self.port = port
        self.auction_doc_id = auction_doc_id
        self.tender_url = 'http://api-sandbox.openprocurement.org/tenders/{0}/auction'.format(auction_doc_id)
        self._auction_data = {}
        self._end_auction_event = Event()
        self.bids_actions = BoundedSemaphore()
        self.database_url = database_url
        self._bids_data = {}
        self.db = couchdb.client.Database('http://localhost:9000/auction')

    def add_bid(self, round_id, bid):
        if round_id not in self._bids_data:
            self._bids_data[round_id] = []
        self._bids_data[round_id].append(bid)

    @property
    def startDate(self):
        date = iso8601.parse_date(
            self._auction_data['data']['period']['startDate']
        )
        if datetime.now(timezone('Europe/Kiev')) > date:
            date = datetime.now(timezone('Europe/Kiev')) + timedelta(seconds=20)
            self._auction_data['data']['period']['startDate'] = date.isoformat()
        return date

    def get_auction_info(self):
        # response = requests.get(self.tender_url)
        # if response.ok:
        #     self._auction_data = response.json()
        # else:
        self._auction_data = {
            "data": {
                "bids": [{
                    "amount": 500,
                    "currency": "UAH",
                    "bidder_id": "0",
                    "time": "2014-10-29T14:15:00+02:00"
                }, {
                    "amount": 485,
                    "currency": "UAH",
                    "bidder_id": "1",
                    "time": "2014-10-29T14:13:00+02:00"
                }],
                "minimalStep": {
                    "amount": 35,
                    "currency": "UAH"
                },
                "period": {
                    "startDate": "2014-10-29T14:13:00+02:00"
                }
            }
        }
        self.bidders_count = len(self._auction_data["data"]["bids"])
        self.bidders_id = [bid["bidder_id"]
                           for bid in self._auction_data["data"]["bids"]]

    def schedule_auction(self):
        self.get_auction_info()
        # Schedule Auction Workflow
        doc = self.db.get(self.auction_doc_id)
        if doc:
            self.db.delete(doc)
        auction_document = {"_id": self.auction_doc_id, "stages": [],
                            "initial_bids": [], "current_stage": -1,
                            "minimalStep": self._auction_data["data"]["minimalStep"]}
        # Initital Bids
        for index in xrange(self.bidders_count):
            auction_document["initial_bids"].append(json.loads(INITIAL_BIDS_TEMPLATE.substitute(
                time="",
                bidder_id=index,
                bidder_name="Bidder #{0}".format(index),
                amount="null"
            )))

        # Schedule PRELIMITARY_BIDS
        prelimitary_bids = json.loads(PRELINARY_BIDS_TEMPLATE.substitute(
            start_time=self.startDate.isoformat()
        ))
        auction_document['stages'].append(prelimitary_bids)
        SCHEDULER.add_job(self.start_auction, 'date', run_date=self.startDate)

        next_stage_timedelta = self.startDate + timedelta(
            seconds=PRELIMITARY_BIDS_SECONDS
        )
        SCHEDULER.add_job(
            self.end_prelimitary_bids, 'date',
            run_date=next_stage_timedelta,
        )
        # Schedule Bids Rounds
        for round_id in xrange(ROUNDS):
            # Schedule PAUSE Stage
            pause_stage = json.loads(PAUSE_TEMPLATE.substitute(
                start_time=next_stage_timedelta.isoformat()
            ))
            auction_document['stages'].append(pause_stage)
            next_stage_timedelta += timedelta(seconds=PAUSE_SECONDS)
            SCHEDULER.add_job(
                self.next_stage, 'date',
                run_date=next_stage_timedelta,
            )

            # Schedule BIDS Stages
            for index in xrange(self.bidders_count):
                bid_stage = json.loads(BIDS_TEMPLATE.substitute(
                    start_time=next_stage_timedelta.isoformat(),
                    bidder_id="",
                    bidder_name="",
                    amount="null",
                    time=""
                ))
                auction_document['stages'].append(bid_stage)
                next_stage_timedelta += timedelta(seconds=BIDS_SECONDS)
                if index == self.bidders_count - 1 and round_id != ROUNDS - 1:
                    SCHEDULER.add_job(
                        self.end_round, 'date',
                        run_date=next_stage_timedelta,
                    )
                else:
                    SCHEDULER.add_job(
                        self.end_bids_stage, 'date',
                        run_date=next_stage_timedelta,
                    )
        announcement = json.loads(ANNOUNCEMENT_TEMPLATE.substitute(
            start_time=next_stage_timedelta.isoformat()
        ))
        auction_document['stages'].append(announcement)

        next_stage_timedelta += timedelta(seconds=ANNOUNCEMENT_SECONDS)
        auction_document['endDate'] = next_stage_timedelta.isoformat()
        self.db.save(auction_document)
        self.server = run_server(self)
        SCHEDULER.add_job(
            self.end_auction, 'date',
            run_date=next_stage_timedelta + timedelta(seconds=20)
        )

    def wait_to_end(self):
        self._end_auction_event.wait()
    
    def start_auction(self):
        logging.info('---------------- Start auction ----------------')
        doc = self.db.get(self.auction_doc_id)
        # Initital Bids
        bids = deepcopy(self._auction_data['data']['bids'])
        doc["initial_bids"] = []
        bids_info = sorting_by_amount(bids)
        for index, bid in enumerate(bids_info):
            doc["initial_bids"].append(json.loads(INITIAL_BIDS_TEMPLATE.substitute(
                time=bid["time"],
                bidder_id=bid["bidder_id"],
                bidder_name="Bidder #{0}".format(bid["bidder_id"]),
                amount=bid["amount"]
            )))
        doc["current_stage"] = 0
        self.db.save(doc)

    def end_prelimitary_bids(self):
        logging.info('---------------- End Prelimitary Bids ----------------')
        self.bids_actions.acquire()
        doc = self.db.get(self.auction_doc_id)
        # TODO: get prelimitary bids
        all_bids = deepcopy(doc["initial_bids"])
        if doc['current_stage'] in self._bids_data:
            all_bids += self._bids_data[doc['current_stage']]

        minimal_bids = []
        for bidder_id in self.bidders_id:
            minimal_bids.append(get_latest_bid_for_bidder(all_bids, bidder_id))
        for index, bid_info in enumerate(sorting_by_amount(minimal_bids)):
            doc["stages"][2 + index] = json.loads(BIDS_TEMPLATE.substitute(
                start_time=doc["stages"][2 + index]["start"],
                bidder_id=bid_info['bidder_id'],
                bidder_name="Bidder #{0}".format(bid_info['bidder_id']),
                amount=bid_info["amount"],
                time=bid_info["time"]
            ))

        prelimitary_bids_results = []
        for index, bid_info in enumerate(sorting_by_time(minimal_bids)):
            prelimitary_bids_results.append(json.loads(BIDS_TEMPLATE.substitute(
                start_time=bid_info["time"],
                bidder_id=bid_info['bidder_id'],
                bidder_name="Bidder #{0}".format(bid_info['bidder_id']),
                amount=bid_info["amount"],
                time=bid_info["time"]
            )))
        doc["stages"][1:1] = prelimitary_bids_results

        doc["current_stage"] += (self.bidders_count + 1)
        self.db.save(doc)
        self.bids_actions.release()

    def approve_bids_information(self, doc):
        all_bids = []
        if doc['current_stage'] in self._bids_data:
            all_bids += self._bids_data[doc['current_stage']]
        if all_bids:
            bid_info = get_latest_bid_for_bidder(
                all_bids, doc["stages"][doc["current_stage"]]['bidder_id']
            )
            doc["stages"][doc["current_stage"]] = json.loads(BIDS_TEMPLATE.substitute(
                start_time=doc["stages"][doc["current_stage"]]["start"],
                bidder_id=bid_info['bidder_id'],
                bidder_name="Bidder #{0}".format(bid_info['bidder_id']),
                amount=bid_info["amount"],
                time=bid_info["time"]
            ))

    def end_round(self):
        self.bids_actions.acquire()
        logging.info('---------------- End Round ----------------')
        doc = self.db.get(self.auction_doc_id)
        self.approve_bids_information(doc)

        round_starts = doc["current_stage"] - self.bidders_count + 1
        round_ends = doc["current_stage"] + 1
        all_bids = deepcopy(doc["stages"][round_starts:round_ends])
            
        minimal_bids = []
        for bidder_id in self.bidders_id:
            minimal_bids.append(get_latest_bid_for_bidder(all_bids, bidder_id))

        for index, bid_info in enumerate(sorting_by_amount(minimal_bids)):
            doc["stages"][doc["current_stage"] + 2 + index] = json.loads(BIDS_TEMPLATE.substitute(
                start_time=doc["stages"][doc["current_stage"] + 2 + index]["start"],
                bidder_id=bid_info['bidder_id'],
                bidder_name="Bidder #{0}".format(bid_info['bidder_id']),
                amount=bid_info["amount"],
                time=bid_info["time"]
            ))
        doc["current_stage"] += 1
        self.db.save(doc)
        self.bids_actions.release()

    def next_stage(self):
        doc = self.db.get(self.auction_doc_id)
        doc["current_stage"] += 1
        self.db.save(doc)
        logging.info('---------------- Start stage {0} ----------------'.format(doc["current_stage"]))

    def end_bids_stage(self):
        self.bids_actions.acquire()
        doc = self.db.get(self.auction_doc_id)
        self.approve_bids_information(doc)
        doc["current_stage"] += 1
        self.db.save(doc)
        logging.info('---------------- Start stage {0} ----------------'.format(doc["current_stage"]))
        self.bids_actions.release()

    def end_auction(self):
        logging.info('---------------- End auction ----------------')
        self.server.stop()
        self.put_auction_data()
        self._end_auction_event.set()

    def put_auction_data(self):
        # response = requests.put(requests.get(self.tender_url), data=self._auction_data)
        # if response.ok:
        #     logging.info('Auction data submitted')
        # else:
        #     logging.warn('Error while submit auction data: {}'.format(response.text))
        pass


def auction_run(auction_doc_id, port, database_url):
    auction = Auction(auction_doc_id, port=port, database_url=database_url)
    SCHEDULER.start()
    auction.schedule_auction()
    auction.wait_to_end()
    SCHEDULER.shutdown()


def main():
    parser = argparse.ArgumentParser(description='---- Auction ----')
    parser.add_argument('auction_doc_id', type=str, help='auction_doc_id')
    parser.add_argument('port', type=int, help='Port')
    parser.add_argument('database_url', type=str, help='Database Url')
    args = parser.parse_args()
    auction_run(args.auction_doc_id, args.port, args.database_url)


##############################################################
if __name__ == "__main__":
    main()
