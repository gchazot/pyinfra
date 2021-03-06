import json

from os import path
from threading import Thread

from six.moves.queue import Queue

from pyinfra import local, logger
from pyinfra.api.exceptions import InventoryError
from pyinfra.progress import progress_spinner

VAGRANT_CONFIG = None
VAGRANT_OPTIONS = None


def _get_vagrant_ssh_config(queue, progress, target):
    logger.debug('Loading SSH config for {0}'.format(target))

    queue.put(local.shell(
        'vagrant ssh-config {0}'.format(target),
        splitlines=True,
    ))

    progress(target)


def _get_vagrant_config(limit=None):
    if limit and not isinstance(limit, list):
        limit = [limit]

    with progress_spinner({'vagrant status'}) as progress:
        output = local.shell(
            'vagrant status --machine-readable',
            splitlines=True,
        )
        progress('vagrant status')

    targets = []

    for line in output:
        _, target, type_, data = line.split(',', 3)

        # Skip anything not in the limit
        if limit is not None and target not in limit:
            continue

        # For each running container - fetch it's SSH config in a thread - this
        # is because Vagrant *really* slow to run each command.
        if type_ == 'state' and data == 'running':
            targets.append(target)

    threads = []
    config_queue = Queue()

    with progress_spinner(targets) as progress:
        for target in targets:
            thread = Thread(
                target=_get_vagrant_ssh_config,
                args=(config_queue, progress, target),
            )
            threads.append(thread)
            thread.start()

    for thread in threads:
        thread.join()

    queue_items = list(config_queue.queue)

    lines = []
    for output in queue_items:
        lines.extend(output)

    return lines


def get_vagrant_config(limit=None):
    global VAGRANT_CONFIG

    if VAGRANT_CONFIG is None:
        logger.info('Getting vagrant config...')

        VAGRANT_CONFIG = _get_vagrant_config(limit=limit)

    return VAGRANT_CONFIG


def get_vagrant_options():
    global VAGRANT_OPTIONS

    if VAGRANT_OPTIONS is None:
        if path.exists('@vagrant.json'):
            with open('@vagrant.json', 'r') as f:
                VAGRANT_OPTIONS = json.loads(f.read())
        else:
            VAGRANT_OPTIONS = {}

    return VAGRANT_OPTIONS


def _make_name_data(host):
    vagrant_options = get_vagrant_options()
    vagrant_host = host['Host']

    # Build data
    data = {
        'ssh_hostname': host['HostName'],
        'ssh_port': host['Port'],
        'ssh_user': host['User'],
        'ssh_key': host['IdentityFile'],
    }

    # Update any configured JSON data
    if vagrant_host in vagrant_options.get('data', {}):
        data.update(vagrant_options['data'][vagrant_host])

    # Work out groups
    groups = vagrant_options.get('groups', {}).get(vagrant_host, [])

    if '@vagrant' not in groups:
        groups.append('@vagrant')

    return '@vagrant/{0}'.format(host['Host']), data, groups


def make_names_data(limit=None):
    vagrant_ssh_info = get_vagrant_config(limit)

    logger.debug('Got Vagrant SSH info: \n{0}'.format(vagrant_ssh_info))

    hosts = []
    current_host = None

    for line in vagrant_ssh_info:
        # Vagrant outputs an empty line between each host
        if not line:
            if current_host:
                hosts.append(_make_name_data(current_host))

            current_host = None
            continue

        key, value = line.split(' ', 1)

        if key == 'Host':
            if current_host:
                hosts.append(_make_name_data(current_host))

            # Set the new host
            current_host = {
                key: value,
            }

        elif current_host:
            current_host[key] = value

        else:
            logger.debug('Extra Vagrant SSH key/value ({0}={1})'.format(
                key, value,
            ))

    if current_host:
        hosts.append(_make_name_data(current_host))

    if not hosts:
        raise InventoryError('No running Vagrant instances found!')

    return hosts
