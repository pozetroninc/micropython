import utime as time
import uhmac as hmac
from uhttp_signature import sign


# Micropython implementations of time() use different epoch starts:
# 1970-01-01 on Unix
# 2000-01-01 on devices
# We use 2000-01-01 00:00:00 UTC for Timestamp header.
try:
    import sys
    if sys.platform == 'linux': # currently the unix port returns 'linux'
        EPOCH = 946684800
    else:
        EPOCH = 0
finally:
    sys = None
    del(sys)

# Max seconds between response Timestamp header and device's current time
MAX_TIMESTAMP_DELTA = 50


class RequestError(Exception):
    pass


class SignatureException(RequestError):
    pass


class HTTPStatusError(RequestError):

    def __init__(self, method, url, response):
        if len(response.content) > 100:
            content = response.content[:100] + b'...'
        else:
            content = response.content
        super(HTTPStatusError, self).__init__('{} {} failed: {} {!r}'
                                              .format(method, url, response.status_code, content))
        del content


def make_request(url, key_id, secret, method, debug, headers, **kwargs):
    #"""
    #Returns Response with HTTP status_code (can be 4xx/5xx error code).
    #Raises RequestError if HTTP request couldn't be completed (e.g. no connection to server).
    #"""
    try:
        # http://server.name:8000/path/and/more?attributes=True
        host_port, path = url.split('//')[1].split('/', 1)
    except ValueError:
        # http://server.name:8000
        host_port = url.split('//')[1].split('/', 1)[0]
        path = ''
    path = '/' + path
    hs = sign.HeaderSigner(key_id=key_id, secret=secret, headers=['(request-target)', 'host', 'timestamp'])
    unsigned = {'host': host_port, 'timestamp': str(int(time.time()) - EPOCH)}
    lower_signed = hs.sign(unsigned, method=method, path=path)
    signed = {}
    signed.update({k[0:1:].upper()+k[1::]: v for k, v in lower_signed.items()})
    del lower_signed

    if headers:
        signed.update(headers)

    try:
        import urequests
        response = getattr(urequests, method.lower())(url, headers=signed, debug=debug, **kwargs)
        del urequests
    except Exception as ex:
        raise RequestError('{} {} failed: {}'.format(method, url, ex))

    if response is None:
        raise RequestError('{} {} failed: network error'.format(method, url))

    return response


def make_validated_request(url, key_id, secret, method='GET', debug=False, headers=None, check_status=True, **kwargs):
    #"""
    #Call make_request() and validate result.
    #1. Check signature and timestamp
    #2. Check HTTP status code
    #"""
    response = make_request(url, key_id, secret, method=method, debug=debug, headers=headers, **kwargs)
    if not hasattr(response, 'content_hmac'):
        if response.content == b'{"detail":"Invalid signature."}':
            raise SignatureException('Request is rejected: Invalid signature')
        raise SignatureException('Response is not signed')
    h = hmac.new(secret, b'timestamp: ')
    h.update(str(response.timestamp))
    h.update(response.text)
    if not hmac.compare_digest(response.content_hmac.encode('ascii'),
                               h.hexdigest()):
        if response.timestamp is None:
            raise SignatureException('Invalid response (no Timestamp)')
        raise SignatureException('Invalid response signature')
    if abs(time.time() - EPOCH - response.timestamp) > MAX_TIMESTAMP_DELTA:
        raise SignatureException('Invalid response (Timestamp is different {!r} vs {!r})'
                                 .format(response.timestamp, time.time() - EPOCH))
    if check_status and not (200 <= response.status_code < 300):
        raise HTTPStatusError(method, url, response)
    return response
