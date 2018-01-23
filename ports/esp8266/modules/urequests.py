import ujson
import usocket
try:
    import ussl
    SUPPORT_SSL = True
except ImportError:
    ussl = None
    SUPPORT_SSL = False

class Response:

    def __init__(self, f):
        self.raw = f
        self.encoding = "utf-8"
        self._cached = None
        self.etag = None

    def close(self):
        if self.raw:
            self.raw.close()
            self.raw = None
        self._cached = None

    @property
    def content(self):
        if self._cached is None:
            self._cached = self.raw.read()
            self.raw.close()
            self.raw = None
        return self._cached

    @property
    def text(self):
        return str(self.content, self.encoding)

    def json(self):
        return ujson.loads(self.content)


def request(method, url, data=None, json=None, headers={}, stream=None, debug=False, out_file=None, in_file=None):
    try:
        proto, dummy, host, path = url.split("/", 3)
    except ValueError:
        proto, dummy, host = url.split("/", 2)
        path = ""
    if proto == 'http:':
        port = 80
    elif proto == 'https:':
        port = 443
    else:
        raise OSError('Unsupported protocol: %s' % proto[:-1])
    if ":" in host:
        host, port = host.split(":", 1)
        port = int(port)

    ai = usocket.getaddrinfo(host, port)
    addr = ai[0][-1]
    s = usocket.socket()
    try:
        s.connect(addr)
        if proto == 'https:':
            if not SUPPORT_SSL: print('HTTPS not supported: could not find ussl')
            s = ussl.wrap_socket(s)
        if debug:
            print(b"%s /%s HTTP/1.0\r\n" % (method, path))
        s.write(b"%s /%s HTTP/1.0\r\n" % (method, path))
        if not "Host" in headers:
            if debug:
                print(b"Host: %s\r\n" % host)
            s.write(b"Host: %s\r\n" % host)
        if json is not None:
            assert data is None
            data = ujson.dumps(json)
            s.write(b'Content-Type: application/json\r\n')
        # Iterate over keys to avoid tuple alloc
        for k in headers:
            if debug:
                print('{}:{}'.format(str(k),str(headers[k])))
            s.write(str(k))
            s.write(b": ")
            s.write(str(headers[k]))
            s.write(b"\r\n")
        if data:
            if debug:
                print(b"Content-Length: {:d}\r\n".format(len(data)))
            s.write(b"Content-Length: {:d}\r\n".format(len(data)))
        elif in_file:
            s.write(b'Content-Type: {}\r\n'.format(headers.get('Content-Type', 'text/plain')))
            import uos
            length = uos.stat(in_file)[6]
            del uos
            if debug:
                print(b"Content-Length: {:d}\r\n".format(length))
            s.write(b"Content-Length: {:d}\r\n".format(length))
        if debug:
            print(b"\r\n")
        s.write(b"\r\n")
        if data:
            if debug:
                print(data)
            s.write(data)
        elif in_file:
            with open(in_file, mode='rb') as infile:
                for l in infile:
                    s.write(l)

        l = s.readline()
        protover, status, msg = l.split(None, 2)
        status = int(status)
        etag = None
        content_hmac = None
        timestamp = None
        if debug: print(l)
        while True:
            l = s.readline()
            if debug:
                print(l)
            if l.startswith(b"Timestamp:"):
                timestamp = int(l[10:].decode())  # cut 'Timestamp:'
            if l.startswith(b"ETag:"):
                etag = str(l).split('"')[1].rsplit('"')[0]
            if l.startswith(b"Content-HMAC:") or l.startswith(b"Content-Hmac:"):
                content_hmac = str(l).split('"')[1].rsplit('"')[0]
            if not l or l == b"\r\n":
                break

            if l.startswith(b"Transfer-Encoding:"):
                if b"chunked" in line:
                    raise ValueError("Unsupported " + l)
            elif l.startswith(b"Location:") and not 200 <= status <= 299:
                raise NotImplementedError("Redirects not yet supported")

        resp = Response(s)
        resp.status_code = status
        resp.reason = msg.rstrip()
        # This removes a RAM usage optimization but allows us to always close the socket in the finally
        if out_file:
            with open(out_file, 'wb') as file:
                buf = s.read(256)
                while buf:
                    file.write(buf)
                    buf = s.read(256)
        else:
            resp._cached = s.read()
            if debug:
                print(resp._cached)
        resp.timestamp = timestamp
        if etag:
            resp.etag = etag
        if content_hmac:
            resp.content_hmac = content_hmac
        return resp
    except OSError as ex:
        print('Error handling response: {}'.format(ex))
    finally:
        s.close()


def head(url, **kw):
    return request("HEAD", url, **kw)

def get(url, **kw):
    return request("GET", url, **kw)

def post(url, **kw):
    return request("POST", url, **kw)

def put(url, **kw):
    return request("PUT", url, **kw)

def patch(url, **kw):
    return request("PATCH", url, **kw)

def delete(url, **kw):
    return request("DELETE", url, **kw)
