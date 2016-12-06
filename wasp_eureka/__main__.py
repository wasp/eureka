"""\
Run a naively scheduled process to perform heartbeats with \
the remote eureka server.

This is especially useful if you need a side-car to a standard python
webapp deployment in which you have many workers, but just need one
reporter.
"""
import asyncio
import contextlib
import logging
import socket
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from http import HTTPStatus

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from wasp_eureka import EurekaClient
from wasp_eureka.exc import EurekaException

with contextlib.suppress(ImportError):
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

logging.basicConfig(level=logging.ERROR,
                    format='%(asctime)-20s %(levelname)5s :: %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger('wasp.eureka')
logger.setLevel(logging.INFO)


def parse_args():
    parser = ArgumentParser(prog='wasp_eureka',
                            description=__doc__,
                            formatter_class=ArgumentDefaultsHelpFormatter)
    # Required
    parser.add_argument('--name', type=str, required=True,
                        help='Application name')
    parser.add_argument('--port', type=int, required=True,
                        help='Exposed server listening port')
    # Optional
    parser.add_argument('--ip', type=str,
                        default=socket.gethostbyname(socket.gethostname()),
                        help='Remotely accessible IP address')
    parser.add_argument('--eureka', type=str,
                        default='http://localhost:8761',
                        help='Target eureka server')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug logging')
    parser.add_argument('--interval', type=int, default=30,
                        help='Heartbeat interval, in seconds')
    parser.add_argument('--instance-id', type=str,
                        help='Optionally set the instance_id')
    parser.add_argument('--health-path', type=str, default='/health',
                        help='Health path')
    parser.add_argument('--status-path', type=str, default='/info',
                        help='Status/Info page path')
    parser.add_argument('--secure', action='store_true',
                        help='Flag to indicate the service is listening on SSL')  # noqa
    return parser.parse_args()


def main():
    args = parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    scheme = 'https' if args.secure else 'http'
    status_url = '{}://{}:{}{}'.format(scheme, args.ip, args.port,
                                       args.status_path)
    health_url = '{}://{}:{}{}'.format(scheme, args.ip, args.port,
                                       args.health_path)
    eureka = EurekaClient(args.name, args.port, args.ip,
                          eureka_url=args.eureka,
                          instance_id=args.instance_id,
                          status_page_url=status_url,
                          health_check_url=health_url)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(eureka.register())
    logger.info('Registered with eureka as %s', eureka.instance_id)

    scheduler = AsyncIOScheduler({'event_loop': loop})

    @scheduler.scheduled_job(IntervalTrigger(seconds=args.interval))
    async def renew_lease():
        try:
            logger.debug('Attempting to renew the lease...')
            await eureka.renew()
            logger.info('Lease renewed')
        except EurekaException as e:
            if e.status == HTTPStatus.NOT_FOUND:
                logger.info('Lease expired, re-registering.')
                await eureka.register()
                return
            logger.error('Error performing renewal: %s', e)

    scheduler.start()
    try:
        logger.info('Running')
        with contextlib.suppress(KeyboardInterrupt):
            loop.run_forever()
    finally:
        scheduler.shutdown()
        loop.run_until_complete(eureka.deregister())
        loop.close()


if __name__ == '__main__':
    main()
