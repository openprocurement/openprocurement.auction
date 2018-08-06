import logging
import iso8601
from datetime import datetime
from dateutil.tz import tzlocal
from yaml import safe_dump as yaml_dump

from openprocurement.auction.utils import generate_request_id, make_request
from openprocurement.auction.worker_core.constants import ROUNDS, TIMEZONE
from openprocurement.auction.worker_core.journal import (
    AUCTION_WORKER_API_AUDIT_LOG_APPROVED,
    AUCTION_WORKER_API_AUDIT_LOG_NOT_APPROVED,
)


LOGGER = logging.getLogger("Auction Worker")


class RequestIDServiceMixin(object):
    """ Simpel mixin class """
    def generate_request_id(self):
        self.request_id = generate_request_id()


class AuditServiceMixin(object):
    """ Mixin class to create, modify and upload audit documents"""
    def prepare_audit(self):
        self.audit = {
            "id": self.auction_doc_id,
            "auctionId": self._auction_data["data"].get("auctionID", ""),
            "auction_id": self.tender_id,
            "items": self._auction_data["data"].get("items", []),
            "timeline": {
                "auction_start": {
                    "initial_bids": []
                }
            }
        }
        if self.lot_id:
            self.audit["lot_id"] = self.lot_id
        for round_number in range(1, ROUNDS + 1):
            self.audit['timeline']['round_{}'.format(round_number)] = {}

    def approve_audit_info_on_bid_stage(self):
        turn_in_round = self.current_stage - (
            self.current_round * (self.bidders_count + 1) - self.bidders_count
        ) + 1
        round_label = 'round_{}'.format(self.current_round)
        turn_label = 'turn_{}'.format(turn_in_round)
        self.audit['timeline'][round_label][turn_label] = {
            'time': datetime.now(tzlocal()).isoformat(),
            'bidder': self.auction_document["stages"][self.current_stage].get('bidder_id', '')
        }
        if self.auction_document["stages"][self.current_stage].get('changed', False):
            self.audit['timeline'][round_label][turn_label]["bid_time"] = self.auction_document["stages"][self.current_stage]['time']
            self.audit['timeline'][round_label][turn_label]["amount"] = self.auction_document["stages"][self.current_stage]['amount']
            if self.features:
                self.audit['timeline'][round_label][turn_label]["amount_features"] = str(
                    self.auction_document["stages"][self.current_stage].get("amount_features")
                )
                self.audit['timeline'][round_label][turn_label]["coeficient"] = str(
                    self.auction_document["stages"][self.current_stage].get("coeficient")
                )

    def approve_audit_info_on_announcement(self, approved={}):
        self.audit['timeline']['results'] = {
            "time": datetime.now(tzlocal()).isoformat(),
            "bids": []
        }
        for bid in self.auction_document['results']:
            bid_result_audit = {
                'bidder': bid['bidder_id'],
                'amount': bid['amount'],
                'time': bid['time']
            }
            if approved:
                bid_result_audit["identification"] = approved[bid['bidder_id']].get('tenderers', [])
                bid_result_audit["owner"] = approved[bid['bidder_id']].get('owner', '')
            self.audit['timeline']['results']['bids'].append(bid_result_audit)

    def upload_audit_file_with_document_service(self, doc_id=None):
        files = {'file': ('audit_{}.yaml'.format(self.auction_doc_id),
                          yaml_dump(self.audit, default_flow_style=False))}
        ds_response = make_request(self.worker_defaults["DOCUMENT_SERVICE"]["url"],
                                   files=files, method='post',
                                   user=self.worker_defaults["DOCUMENT_SERVICE"]["username"],
                                   password=self.worker_defaults["DOCUMENT_SERVICE"]["password"],
                                   session=self.session_ds, retry_count=3)

        if doc_id:
            method = 'put'
            path = self.tender_url + '/documents/{}'.format(doc_id)
        else:
            method = 'post'
            path = self.tender_url + '/documents'

        response = make_request(path, data=ds_response,
                                user=self.worker_defaults["resource_api_token"],
                                method=method, request_id=self.request_id, session=self.session,
                                retry_count=2
                                )
        if response:
            doc_id = response["data"]['id']
            LOGGER.info(
                "Audit log approved. Document id: {}".format(doc_id),
                extra={"JOURNAL_REQUEST_ID": self.request_id,
                       "MESSAGE_ID": AUCTION_WORKER_API_AUDIT_LOG_APPROVED}
            )
            return doc_id
        else:
            LOGGER.warning(
                "Audit log not approved.",
                extra={"JOURNAL_REQUEST_ID": self.request_id,
                       "MESSAGE_ID": AUCTION_WORKER_API_AUDIT_LOG_NOT_APPROVED})

    def upload_audit_file_without_document_service(self, doc_id=None):
        files = {'file': ('audit_{}.yaml'.format(self.auction_doc_id),
                          yaml_dump(self.audit, default_flow_style=False))}
        if doc_id:
            method = 'put'
            path = self.tender_url + '/documents/{}'.format(doc_id)
        else:
            method = 'post'
            path = self.tender_url + '/documents'

        response = make_request(path, files=files,
                                user=self.worker_defaults["resource_api_token"],
                                method=method, request_id=self.request_id, session=self.session,
                                retry_count=2
                                )
        if response:
            doc_id = response["data"]['id']
            LOGGER.info(
                "Audit log approved. Document id: {}".format(doc_id),
                extra={"JOURNAL_REQUEST_ID": self.request_id,
                       "MESSAGE_ID": AUCTION_WORKER_API_AUDIT_LOG_APPROVED}
            )
            return doc_id
        else:
            LOGGER.warning(
                "Audit log not approved.",
                extra={"JOURNAL_REQUEST_ID": self.request_id,
                       "MESSAGE_ID": AUCTION_WORKER_API_AUDIT_LOG_NOT_APPROVED})


class DateTimeServiceMixin(object):
    """ Simple time convertion mixin"""

    def convert_datetime(self, datetime_stamp):
        return iso8601.parse_date(datetime_stamp).astimezone(TIMEZONE)
