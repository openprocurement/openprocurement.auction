import logging
import iso8601
from datetime import datetime
from dateutil.tz import tzlocal
from yaml import safe_dump as yaml_dump

from openprocurement.auction.utils import generate_request_id, make_request
from openprocurement.auction.worker_core.constants import TIMEZONE
from openprocurement.auction.worker_core.journal import (
    AUCTION_WORKER_API_AUDIT_LOG_APPROVED,
    AUCTION_WORKER_API_AUDIT_LOG_NOT_APPROVED,
)


LOGGER = logging.getLogger("Auction Worker")


class RequestIDServiceMixin(object):
    """ Simple mixin class """
    def generate_request_id(self):
        self.request_id = generate_request_id()


class AuditServiceMixin(object):
    """ Mixin class to create, modify and upload audit documents"""
    def prepare_audit(self):
        raise NotImplementedError

    def approve_audit_info_on_announcement(self, approved={}):
        raise NotImplementedError

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
