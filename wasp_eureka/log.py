import logging


class InstanceIdLogAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        return '[%s] %s' % (self.extra['instance_id'], msg), kwargs


logger = logging.getLogger('wasp.eureka')
