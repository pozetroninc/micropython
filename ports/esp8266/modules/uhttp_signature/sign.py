import base64
#import six

#from cryptography.hazmat.backends import default_backend
#from cryptography.hazmat.primitives import hashes, hmac, serialization
#from cryptography.hazmat.primitives.asymmetric import rsa, padding

import gc

try:
    import uhmac as hmac
except ImportError:
    import hmac

from . import utils

DEFAULT_SIGN_ALGORITHM = "hmac-sha256"

class Signer(object):
    #"""
    #When using an RSA algo, the secret is a PEM-encoded private or public key.
    #When using an HMAC algo, the secret is the HMAC signing secret.

    #Password-protected keyfiles are not supported.
    #"""

    def __init__(self, secret, algorithm=None):
        if algorithm is None:
            algorithm = DEFAULT_SIGN_ALGORITHM

        assert algorithm in utils.ALGORITHMS, "Unknown algorithm"
        # Removing the reference to six, now need to have a check for a bytes type
        # TODO RSA cannot be reintroduced without this changing again.
        #if isinstance(secret, six.string_types): secret = secret.encode("ascii")
        if not isinstance(secret, (bytes, bytearray)):
            raise TypeError("secret: expected bytes or bytearray, but got %r" % type(secret).__name__)

        # TODO RSA cannot be reintroduced without this changing again.
        #self._rsa_public = None
        #self._rsa_private = None
        self._hash = None
        self.sign_algorithm, self.hash_algorithm = algorithm.split('-')

        # TODO RSA cannot be reintroduced without this changing again.
        #if self.sign_algorithm == 'rsa':

            #try:
                #self._rsahash = utils.HASHES[self.hash_algorithm]
                #self._rsa_private = serialization.load_pem_private_key(secret,
                                                                       #None,
                                                                       #backend=default_backend())
                #self._rsa_public = self._rsa_private.public_key()
            #except ValueError as e:
                #try:
                    #self._rsa_public = serialization.load_pem_public_key(secret,
                                                                         #backend=default_backend())
                #except ValueError as e:
                    #raise utils.HttpSigException("Invalid key.")

        if self.sign_algorithm == 'hmac':
            self._hash = True
            self.secret = secret

    @property
    def algorithm(self):
        gc.collect()
        return '%s-%s' % (self.sign_algorithm, self.hash_algorithm)

    # TODO RSA cannot be reintroduced without this changing again.
    #def _sign_rsa(self, data):
        #if isinstance(data, six.string_types): data = data.encode("ascii")
        #r = self._rsa_private.signer(padding.PKCS1v15(), self._rsahash())
        #r.update(data)
        #return r.finalize()

    def _sign_hmac(self, data):
        # TODO RSA cannot be reintroduced without this changing again.
        #if isinstance(data, six.string_types): data = data.encode("ascii")
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("data: expected bytes or bytearray, but got %r" % type(data).__name__)
        hmac_instance = hmac.new(self.secret, digestmod=utils.HASHES[self.hash_algorithm])
        hmac_instance.update(data)
        gc.collect()
        return hmac_instance.digest()

    def _sign(self, data):
        # TODO RSA cannot be reintroduced without this changing again.
        #if isinstance(data, six.string_types): data = data.encode("ascii")
        if not isinstance(data, (bytes, bytearray)):
            gc.collect()
            raise TypeError("data: expected bytes or bytearray, but got %r" % type(data).__name__)
        signed = None
        #if self._rsa_private:
            #signed = self._sign_rsa(data)
        if self._hash:
            signed = self._sign_hmac(data)
        if not signed:
            gc.collect()
            raise ValueError('No valid encryptor found.')
        gc.collect()
        return base64.b64encode(signed).decode("ascii")


class HeaderSigner(Signer):
    #'''
    #Generic object that will sign headers as a dictionary using the http-signature scheme.
    #https://github.com/joyent/node-http-signature/blob/master/http_signing.md

    #:arg key_id:    the mandatory label indicating to the server which secret to use
    #:arg secret:    a PEM-encoded RSA private key or an HMAC secret (must match the algorithm)
    #:arg algorithm: one of the six specified algorithms
    #:arg headers:   a list of http headers to be included in the signing string, defaulting to ['timestamp'].
    #'''

    def __init__(self, key_id, secret, algorithm=None, headers=None):
        if algorithm is None:
            algorithm = DEFAULT_SIGN_ALGORITHM

        super(HeaderSigner, self).__init__(secret=secret, algorithm=algorithm)
        self.headers = headers or ['timestamp']
        self.signature_template = utils.build_signature_template(key_id, algorithm, headers)


    def sign(self, arg_headers, host=None, method=None, path=None):
        #"""
        #Add Signature Authorization header to case-insensitive header dict.

        #headers is a case-insensitive dict of mutable headers.
        #host is a override for the 'host' header (defaults to value in headers).
        #method is the HTTP method (required when using '(request-target)').
        #path is the HTTP path (required when using '(request-target)').
        #"""
        headers = {}
        headers.update((k.lower(), v) for k, v in arg_headers.items())
        signable = utils.generate_message(self.headers, headers, host, method, path)

        signature = self._sign(signable)
        headers['authorization'] = self.signature_template % signature

        gc.collect()
        return headers
