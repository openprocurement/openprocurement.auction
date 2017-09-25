import socket
from random import sample
from urlparse import urlparse
from couchdb import Server, Session
from time import sleep

CONSTANT_IS_TRUE = True


def couchdb_dns_query_settings(server_url, database_name):
    parsed_url = urlparse(server_url)
    all_ips = set([str(i[4][0]) for i in socket.getaddrinfo(urlparse(server_url).hostname, 80)])

    while all_ips:
        selected_ip = set(sample(all_ips, 1))
        all_ips -= selected_ip
        couch_url = server_url.replace(parsed_url.hostname, selected_ip.pop())
        try:
            server = Server(couch_url, session=Session(retry_delays=range(10)))
            return server[database_name]
        except socket.error:
            continue
    raise Exception("No route to any couchdb server")


def iterview(server_url, database_name, view_name, sleep_seconds=10, wrapper=None, **options):
    """Iterate the rows in a view, fetching rows in batches and yielding
    one row at a time.

    Since the view's rows are fetched in batches any rows emitted for
    documents added, changed or deleted between requests may be missed or
    repeated.

    :param name: the name of the view; for custom views, use the format
                 ``design_docid/viewname``, that is, the document ID of the
                 design document and the name of the view, separated by a
                 slash.
    :param batch: number of rows to fetch per HTTP request.
    :param wrapper: an optional callable that should be used to wrap the
                    result rows
    :param options: optional query string parameters
    :return: row generator
    """
    database = couchdb_dns_query_settings(server_url, database_name)
    start_key = 0
    options['start_key'] = start_key
    options['limit'] = 1000
    while CONSTANT_IS_TRUE:
        try:
            rows = list(database.view(view_name, wrapper, **options))
        except socket.error:
            options['start_key'] = 0
            database = couchdb_dns_query_settings(server_url, database_name)
            continue
        if len(rows) != 0:
            for row in rows:
                start_key = row['key']
                yield row
        else:
            sleep(sleep_seconds)
        options['start_key'] = (start_key + 1)
