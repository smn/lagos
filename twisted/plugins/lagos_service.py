from zope.interface import implements
from twisted.python import log, usage
from twisted.application.service import IServiceMaker, Service
from twisted.plugin import IPlugin
from twisted.internet.defer import Deferred
from twisted.internet import reactor
from twisted.web.client import Agent
import pygsm

class Options(usage.Options):
    optParameters = [
        ["port", "p", "/dev/ttyACM0", "The port where the GSM is connected"],
        ["uri", "u", None, "Where to POST the SMS, http://user:pw@host/resource"],
    ]

class LagosService(Service):
    def __init__(self, uri, **modem_options):
        self.uri = uri
        self.modem_options = modem_options
        self.agent = Agent(reactor)

    def startService(self):
        log.msg("Starting Lagos")
        self.connect_modem()
    
    def connect_modem(self):
        log.msg("Connecting modem")
        self.modem = pygsm.GsmModem(**self.modem_options).boot()
        self.wait_for_network()
    
    def wait_for_network(self):
        log.msg("Waiting for network connection")
        self.modem.wait_for_network()
        log.msg("Got network connection, signal strength: %s" % \
                    self.modem.signal_strength())
        self.poll_messages()

    def poll_messages(self):
        log.msg("Polling for messages")
        deferred = Deferred()
        deferred.addCallback(self.post_message)
        deferred.addErrback(log.err)
        deferred.callback(self.modem.next_message())
        return deferred
    
    def post_message(self, message):
        if message:
            log.msg("Posting %s to %s" % (message, self.uri))
            # deferred = self.agent.request('POST', self.uri, headers, body)
        else:
            log.msg("No messages available, checking again after 1 second")
        reactor.callLater(1, self.poll_messages)       
 
    def disconnect_modem(self):
        log.msg("Disconnecting modem")

    def stopService(self):
        log.msg("Stopping Lagos")
        self.disconnect_modem()

   

class LagosServiceMaker(object):
    implements(IServiceMaker, IPlugin)
    tapname = "lagos"
    description = "POST incoming SMSs to a URL"
    options = Options
    
    def makeService(self, options):
        options.update({
            "logger": pygsm.GsmModem.debug_logger
        })
        return LagosService(**options)
    

serviceMaker = LagosServiceMaker()

