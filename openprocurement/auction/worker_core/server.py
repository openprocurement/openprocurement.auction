from gevent.pywsgi import WSGIServer, WSGIHandler
from gevent import socket
import errno
from openprocurement.auction.utils import prepare_extra_journal_fields


class _LoggerStream(object):
    """
    Logging workaround for Gevent PyWSGI Server
    """
    def __init__(self, logger):
        super(_LoggerStream, self).__init__()
        self.logger = logger

    def write(self, msg, **kw):
        self.logger.info(msg, **kw)


class AuctionsWSGIHandler(WSGIHandler):

    def run_application(self):
        try:
            return super(AuctionsWSGIHandler, self).run_application()
        except socket.error as ex:
            if ex.args[0] in (errno.EPIPE, errno.ECONNRESET):
                self.close_connection = True
            else:
                raise ex

    def log_request(self):
        log = self.server.log
        if log:
            extra = prepare_extra_journal_fields(self.headers)
            real_ip = self.environ.get('HTTP_X_REAL_IP', '')
            if real_ip.startswith('172.'):
                real_ip = ''
            extra['JOURNAL_REMOTE_ADDR'] = ','.join(
                [self.environ.get('HTTP_X_FORWARDED_FOR', ''), real_ip]
            )
            extra['JOURNAL_USER_AGENT'] = self.environ.get('HTTP_USER_AGENT', '')

            log.write(self.format_request(), extra=extra)
