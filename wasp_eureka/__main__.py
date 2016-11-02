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

from wasp_eureka import EurekaClient

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger('wasp.eureka')


async def run_scheduler(eureka, *, interval=30, loop=None):
    """Schedules the renewal to be performed, tasks
    are scheduled in the event loop on the interval,
    ignoring previous task run-times."""
    if loop is None:
        loop = asyncio.get_event_loop()

    def log_on_err(future) -> None:
        if future.exception():
            logger.error('Error during task: %s', future.exception())
        else:
            logger.debug('Task complete.')

    logger.info('Scheduling task every %s seconds.', interval)
    while True:
        await asyncio.sleep(interval, loop=loop)
        logger.debug('Firing task.')
        task = loop.create_task(eureka.renew())
        task.add_done_callback(log_on_err)


def main():
    parser = ArgumentParser(prog='wasp_eureka',
                            description=__doc__,
                            formatter_class=ArgumentDefaultsHelpFormatter)  # noqa

    parser.add_argument('--name', type=str, required=True,
                        help='Application name')
    parser.add_argument('--port', type=int, required=True,
                        help='Exposed server listening port')
    parser.add_argument('--ip', type=str,
                        default=socket.gethostbyname(socket.gethostname()),
                        help='Remotely accessible IP address')
    parser.add_argument('--eureka', type=str,
                        default='http://localhost:8761/eureka/',
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
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    status_url = 'http://{}:{}{}'.format(args.instance_id, args.port,
                                         args.status_path)
    health_url = 'http://{}:{}{}'.format(args.instance_id, args.port,
                                         args.health_path)
    eureka = EurekaClient(args.name, args.port, args.ip,
                          eureka_url=args.eureka,
                          instance_id=args.instance_id,
                          status_page_url=status_url,
                          health_check_url=health_url)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(eureka.register())
    scheduler_task = loop.create_task(run_scheduler(eureka,
                                                    interval=args.interval))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        with contextlib.suppress(asyncio.CancelledError):
            scheduler_task.cancel()
        asyncio.gather(scheduler_task, loop=loop)
        loop.run_until_complete(eureka.deregister())
        loop.close()


if __name__ == '__main__':
    main()
