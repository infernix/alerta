
import os
import sys
import subprocess
import shlex
import re

from alerta.common import log as logging
from alerta.common import config
from alerta.alert import Alert, Heartbeat, severity
from alerta.common.mq import Messaging

Version = '2.0.0'

LOG = logging.getLogger(__name__)
CONF = config.CONF


class CheckerClient(object):
    def main(self):

        if CONF.heartbeat:
            msg = Heartbeat(version=Version)
        else:
            # Run Nagios plugin check
            args = shlex.split(os.path.join(CONF.nagios_plugins, CONF.nagios_cmd))
            LOG.info('Running %s', ' '.join(args))
            try:
                check = subprocess.Popen(args, stdout=subprocess.PIPE)
            except Exception, e:
                LOG.error('Nagios check did not execute: %s', e)
                sys.exit(1)

            stdout = check.communicate()[0]
            rc = check.returncode
            LOG.debug('Nagios plugin %s => %s (rc=%d)', CONF.nagios_cmd, stdout, rc)


            if rc == 0:
                sev = severity.NORMAL
            elif rc == 1:
                sev = severity.WARNING
            elif rc == 2:
                sev = severity.CRITICAL
            elif rc == 3:
                sev = severity.UNKNOWN
            else:
                rc = -1
                sev = severity.INDETERMINATE

            # Parse Nagios plugin check output
            text = ''
            long_text = ''
            perf_data = ''
            extra_perf_data = False

            for num, line in enumerate(stdout.split('\n'), start=1):
                if num == 1:
                    if '|' in line:
                        text = line.split('|')[0].rstrip(' ')
                        perf_data = line.split('|')[1]
                        value = perf_data.split(';')[0].lstrip(' ')
                    else:
                        text = line
                        value = 'rc=%s' % rc
                else:
                    if '|' in line:
                        long_text += line.split('|')[0]
                        perf_data += line.split('|')[1]
                        extra_perf_data = True
                    elif extra_perf_data is False:
                        long_text += line
                    else:
                        perf_data += line

            LOG.debug('Short Output: %s', text)
            LOG.debug('Long Output: %s', long_text)
            LOG.debug('Perf Data: %s', perf_data)

            msg = Alert(
                resource=CONF.resource,
                event=CONF.event,
                correlate=CONF.correlate,
                group=CONF.group,
                value=value,
                severity=sev,
                environment=CONF.environment,
                service=CONF.service,
                text=text + ' ' + long_text,
                event_type='nagiosAlert',
                tags=CONF.tags,
                threshold_info=CONF.nagios_cmd,
                timeout=CONF.timeout,
                # more_info=perf_data,
                raw_data=stdout,
            )

        if CONF.dry_run:
            print msg
        else:
            LOG.debug('Message => %s', repr(msg))

            mq = Messaging()
            mq.connect()
            mq.send(msg)
            mq.disconnect()

        return msg.get_id()