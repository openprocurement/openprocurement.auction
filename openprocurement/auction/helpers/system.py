from socket import gethostname, gethostbyname
from gevent.pywsgi import WSGIServer
from gevent.baseserver import parse_address

def free_memory():
    """
    Get memory usage
    """
    with open('/proc/meminfo', 'r') as mem:
        ret = {'free': 0.0, 'total': 0.0}

        for i in mem:
            sline = i.split()
            if str(sline[0]) in ('MemTotal:', 'SwapTotal:'):
                ret['total'] += int(sline[1])
            elif str(sline[0]) in ('MemFree:', 'MemAvailable:', 'SwapFree:'):
                ret['free'] += int(sline[1])
    return float(ret['free']) / ret['total']


def get_ip_address():
    return gethostbyname(gethostname())


def get_lisener(port, host=''):
    if not host:
        host = get_ip_address()
    lisener = None
    while lisener is None:
        family, address = parse_address((host, port))
        try:
            lisener = WSGIServer.get_listener(address, family=family)
        except Exception, e:
            pass
        port += 1
    return lisener