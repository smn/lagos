from __future__ import with_statement
from contextlib import closing
from datetime import datetime
from urlparse import urlsplit
from base64 import b64encode
from twisted.python import log
from twisted.internet import reactor, ssl
from twisted.web import client
import os.path
import shutil
import urllib

try:
    import cPickle as pickle
except ImportError:
    import pickle


def load_queue_from_disk(filename):
    """
    Load the old queue from disk when started. Old messages that weren't
    posted yet are read from the queue and processed.
    """
    if os.path.exists(filename):
        log.msg("Loading queue from %s" % filename)
        try:
            with closing(open(filename, 'r')) as fp:
                data = pickle.load(fp)
            return data
        except IOError, e:
            log.err()
            backup_filename = "%s.%s" % (
                filename, 
                datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            )
            shutil.copyfile(filename, backup_filename)
            log.err("Couldn't load queue from %s, backed it up to %s" % (
                filename, backup_filename
            ))
    
    # return an empty queue, start from scratch.
    return []

def save_queue_to_disk(filename, queue):
    """
    Save the queue to disk when shutting down, makes sure we don't
    lose any messages during shutdown & restart.
    """
    log.msg("Saving queue to %s" % filename)
    with closing(open(filename, 'w+')) as fp:
        pickle.dump(queue, fp)


def request(url, data={}, method='POST'):
    """
    Post the given dictionary to the URL.
    """
    url_info = urlsplit(url)
    
    # determine what port we're on
    if url_info.scheme == 'https':
        context_factory = ssl.ClientContextFactory()
        port = url_info.port or 443
    elif url_info.scheme == 'http':
        context_factory = None
        port = url_info.port or 80
    else:
        raise RuntimeError, 'unsupported URL request scheme %s' % url_info.scheme
    
    # Twisted doesn't understand it when auth credentials are passed along
    # in the URI, remove those (ie scheme://user:password@host/path)
    url_without_auth = "%s://%s:%s%s" % (
        url_info.scheme, url_info.hostname, port, url_info.path
    )
    
    # specify the headers
    headers = {}
    # specify the kwargs for the getPage call
    kwargs = {}
    if method == 'POST' and data:
        # we're doing a form type post, set the header accordingly
        headers.update({
            'Content-Type': 'application/x-www-form-urlencoded',
        })
        kwargs.update({
            'postdata': urllib.urlencode(data)
        })
    
    # Encode the credentials to send them as an HTTP Header
    if url_info.username and url_info.password:
        b64_credentials = b64encode("%s:%s" % (url_info.username, url_info.password))
        headers.update({
          'Authorization': 'Basic %s' % b64_credentials
        })
        
    kwargs.update({
        'headers': headers,
        'agent': 'Lagos SMS - http://github.com/smn/lagos',
        'method': method
    })
    return client.getPage(url_without_auth, context_factory, **kwargs)
