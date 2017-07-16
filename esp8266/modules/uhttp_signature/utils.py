
try:
    import ure as re
except ImportError:
    import re
import ustruct
#import uhashlib as hashlib
import base64
#import six
import gc

#from cryptography.hazmat.primitives.hashes import SHA1, SHA256, SHA512
#from uhashlib import sha1, sha256


# TODO RSA cannot be reintroduced without this changing again.
#ALGORITHMS = frozenset(['rsa-sha1', 'rsa-sha256', 'rsa-sha512', 'hmac-sha1', 'hmac-sha256', 'hmac-sha512'])
ALGORITHMS = frozenset(['hmac-sha1', 'hmac-sha256'])
HASHES = {'sha1':   'sha1',
          'sha256': 'sha256'}#,
          #'sha512': SHA512}


def parse_http_list(s):
    #"""Parse lists as described by RFC 2068 Section 2.
    #In particular, parse comma-separated lists where the elements of
    #the list may include quoted-strings.  A quoted-string could
    #contain a comma.  A non-quoted string could have quotes in the
    #middle.  Neither commas nor quotes count if they are escaped.
    #Only double-quotes count, not single-quotes.
    #"""
    res = []
    part = ''

    escape = quote = False
    for cur in s:
        if escape:
            part += cur
            escape = False
            continue
        if quote:
            if cur == '\\':
                escape = True
                continue
            elif cur == '"':
                quote = False
            part += cur
            continue

        if cur == ',':
            res.append(part)
            part = ''
            continue

        if cur == '"':
            quote = True

        part += cur

    # append last part
    if part:
        res.append(part)

    return [part.strip() for part in res]


class HttpSigException(Exception):
    pass


def generate_message(required_headers, headers, host, method, path):

    if not required_headers:
        required_headers = ['timestamp']

    signable_list = []
    for h in required_headers:
        h = h.lower()
        if h == '(request-target)':
            if not method or not path:
                gc.collect()
                raise Exception('method and path arguments required when using "(request-target)"')
            signable_list.append('%s: %s %s' % (h, method.lower(), path))

        elif h == 'host':
            # 'host' special case due to requests lib restrictions
            # 'host' is not available when adding auth so must use a param
            # if no param used, defaults back to the 'host' header
            if not host:
                if 'host' in headers:
                    host = headers[h]
                else:
                    gc.collect()
                    raise Exception('missing required header "%s"' % (h))
            signable_list.append('%s: %s' % (h, host))
        else:
            if h not in headers:
                gc.collect()
                raise Exception('missing required header "%s"' % (h))

            signable_list.append('%s: %s' % (h, headers[h]))

    signable = '\n'.join(signable_list).encode("ascii")
    gc.collect()
    return signable


def parse_authorization_header(header):
    #if not isinstance(header, six.string_types):
        #header = header.decode("ascii") #HTTP headers cannot be Unicode.
    if isinstance(header, (bytes, bytearray)):
        header = str(header)

    auth = header.split(" ", 1)
    if len(auth) > 2:
        gc.collect()
        raise ValueError('Invalid authorization header. (eg. Method key1=value1,key2="value, \"2\"")')

    # Split up any args into a dictionary.
    values = {}
    if len(auth) == 2:
        auth_value = auth[1]
        if auth_value and len(auth_value):
            # This is tricky string magic.  Let urllib do it.
            fields = parse_http_list(auth_value)

            for item in fields:
                # Only include keypairs.
                if '=' in item:
                    # Split on the first '=' only.
                    key, value = item.split('=', 1)
                    if not (len(key) and len(value)):
                        continue

                    # Unquote values, if quoted.
                    if value[0] == '"':
                        value = value[1:-1]

                    values[key] = value

    # ("Signature", {"headers": "timestamp", "algorithm": "hmac-sha256", ... })
    gc.collect()
    return (auth[0], values)


def build_signature_template(key_id, algorithm, headers):
    #"""
    #Build the Signature template for use with the Authorization header.

    #key_id is the mandatory label indicating to the server which secret to use
    #algorithm is one of the six specified algorithms
    #headers is a list of http headers to be included in the signing string.

    #The signature must be interpolated into the template to get the final Authorization header value.
    #"""
    param_map = {'keyId': key_id,
                 'algorithm': algorithm,
                 'signature': '%s'}
    if headers:
        headers = [h.lower() for h in headers]
        param_map['headers'] = ' '.join(headers)
    kv = ['{0}="{1}"'.format(key, value) for key,value in param_map.items()]
    kv_string = ','.join(kv)
    sig_string = 'Signature {0}'.format(kv_string)
    gc.collect()
    return sig_string


# TODO RSA cannot be reintroduced without this changing again.
#def is_rsa(keyobj):
    #return lkv(keyobj.blob)[0] == "ssh-rsa"

# based on http://stackoverflow.com/a/2082169/151401
# No amount of messing around got the below working on MicroPython
#class CaseInsensitiveDict(dict):

    #def __init__(self, d=None, **kwargs):
        #super(CaseInsensitiveDict, self).__init__(**kwargs)
        #if d:
            ##self.update((k.lower(), v) for k, v in six.iteritems(d))
            #for k, v in d.items():
                #print("key is {} and value is {}".format(k, v))
            #self.update((k.lower(), v) for k, v in d.items())
            #try:
                #self.pop(k)
            #except KeyError:
                ## Python 3 -> MicroPython implementation difference
                #pass
            #print('done')

    #def __setitem__(self, key, value):
        #print("key is {} and value is ".format(key, value))
        #super(CaseInsensitiveDict, self).__setitem__(key.lower(), value)

    #def __getitem__(self, key):
        #return super(CaseInsensitiveDict, self).__getitem__(key.lower())

    #def __contains__(self, key):
        #dir(super)
        #return super(CaseInsensitiveDict, self).__contains__(key.lower())

# currently busted...
#def get_fingerprint(key):
    #"""
    #Takes an ssh public key and generates the fingerprint.

    #See: http://tools.ietf.org/html/rfc4716 for more info
    #"""
    #if key.startswith('ssh-rsa'):
        #key = key.split(' ')[1]
    #else:
        #regex = r'\-{4,5}[\w|| ]+\-{4,5}'
        #key = re.split(regex, key)[1]

    #key = key.replace('\n', '')
    #key = key.strip().encode('ascii')
    #key = base64.b64decode(key)
    #fp_plain = hashlib.md5(key).hexdigest()
    #return ':'.join(a+b for a,b in zip(fp_plain[::2], fp_plain[1::2]))


