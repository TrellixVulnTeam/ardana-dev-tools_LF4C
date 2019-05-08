#!/usr/bin/env python
#
# (c) Copyright 2017 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017-2018 SUSE LLC
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
# Runs in the deployer.
#

import argparse
import logging
import os
import sys
import yaml

log_file = os.path.splitext(sys.argv[0])[0] + '.log'
logging.basicConfig(level=logging.INFO, filename=log_file,
                    format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class InvalidCloudNameError(StandardError):
    def __init__(self, *args, **kwargs):
        super(InvalidCloudNameError, self).__init__(*args, **kwargs)


class NoCloudNameError(StandardError):
    def __init__(self, *args, **kwargs):
        super(NoCloudNameError, self).__init__(*args, **kwargs)


class InvalidArdanaCIBasePathError(StandardError):
    def __init__(self, *args, **kwargs):
        super(InvalidArdanaCIBasePathError, self).__init__(*args, **kwargs)


class InvalidArdanaCICloudPathError(StandardError):
    def __init__(self, *args, **kwargs):
        super(InvalidArdanaCICloudPathError, self).__init__(*args, **kwargs)


class InvalidServersPathError(StandardError):
    def __init__(self, *args, **kwargs):
        super(InvalidServersPathError, self).__init__(*args, **kwargs)


class InvalidDistroIDError(StandardError):
    def __init__(self, *args, **kwargs):
        super(InvalidDistroIDError, self).__init__(*args, **kwargs)


class Servers(object):

    def __init__(self, cloud=None, ci_base=None, distro=None, distros=None, arch=None):
        if cloud is None:
            raise NoCloudNameError("No cloud name specified when creating "
                                   "%s object" % (self.__class__.__name__))

        if ci_base is None:
            ci_base = os.path.join(os.environ["HOME"], "ardana-ci")

        if not os.path.exists(ci_base):
            raise InvalidArdanaCIBasePathError("Invalid ardana-ci directory: '%s'" %
                                           ci_base)

        cloud_base = os.path.join(ci_base, cloud)
        if not os.path.exists(cloud_base):
            raise InvalidArdanaCICloudPathError("Specified ardana-ci cloud directory "
                                            "doesn't exist: '%s'" %
                                            cloud_base)

        servers_file = os.path.join(cloud_base, "data", "servers.yml")
        if not os.path.exists(servers_file):
            raise InvalidArdanaCICloudPathError("Specified servers file doesn't "
                                            "exist: '%s'" % servers_file)

        if distro is None:
            distro = "sles"

        if distros is None:
            distros = dict(sles='sles12sp4', rhel='rhel75')

        if arch is None:
            arch = 'x86_64'

        self._cloud = cloud
        self._distro = distro
        self._distros = distros
        self._arch = arch
        self._ci_base = ci_base
        self._cloud_base = cloud_base
        self._servers_file = servers_file
        self._servers_data = None
        self._dirty = False

    @property
    def cloud(self):
        return self._cloud

    @property
    def arch(self):
        return self._arch

    @property
    def default_distro(self):
        return self._distro

    @property
    def distros(self):
        return self._distros

    @property
    def ci_base(self):
        return self._ci_base

    @property
    def cloud_base(self):
        return self._cloud_base

    @property
    def servers_file(self):
        return self._servers_file

    @property
    def servers_data(self):
        if self._servers_data is None:
            self._load_servers()

        return self._servers_data

    @property
    def dirty(self):
        return self._dirty

    @property
    def servers(self):
        return list(self.servers_data['servers'])

    def _load_servers(self):
        with open(self.servers_file) as fp:
            self._servers_data = yaml.load(fp)

    def _save_servers(self):
        with open(self.servers_file, "w") as fp:
            yaml.dump(self._servers_data, fp, default_flow_style=False,
                      indent=4)

    def commit(self):
        if self.dirty and self._servers_data:
            logger.info('Server state changed, saving')
            self._save_servers()
        else:
            logger.info('Server state did not change, not saving')

    def _gen_distro_id(self, distro=None, arch=None):
        if distro is None:
            distro = self.default_distro
        if arch is None:
            arch = self.arch

        distro_version = self.distros.get(distro, None)
        if distro_version is None:
            raise InvalidDistroIDError("'%s' is not a valid distro")

        return "%s-%s" % (distro_version, arch)

    def set_distro_id(self, server, distro=None, arch=None):
        if distro is None:
            distro = self.default_distro

        logger.info("Setting distro for node '%s' (role '%s') to '%s'" %
                    (server['id'], server['role'], distro))

        distro_id = self._gen_distro_id(distro, arch)

        # We want to be able to exercise the "default" distro mechanism
        # so remove a distro-id entry if one exists when the default
        # distro is specified for a server.
        if distro == self.default_distro:
            if "distro-id" in server:
                logger.info("The distro ('%s') specified for server "
                            "'%s' is the default, removing existing "
                            "'distro-id' entry" % (distro, server['id']))
                del server["distro-id"]

                # mark servers object as dirty
                self._dirty = True
        else:
            if "distro-id" in server:
                action = "Updating"
            else:
                action = "Setting"
            logger.info("%s the 'distro-id' entry for server '%s' to '%s'" %
                        (action, server['id'], distro_id))
            server["distro-id"] = distro_id

            # mark servers object as dirty
            self._dirty = True

        logger.info("Server '%s' distro_id '%s' (default '%s')" %
                    (server['id'], server.get('distro-id', "(default)"),
                     distro_id))


def main():

    parser = argparse.ArgumentParser(description='Configure compute distros')
    parser.add_argument('cloud',
                        help='Name of cloud being deployed')
    parser.add_argument('--default-distro', dest='default_distro',
                        type=str, choices=['sles', 'rhel'], default='sles',
                        help='Default linux distribution')

    # limit set of nodes to be cobbled
    parser.add_argument('--nodes', dest='cobble_nodes', default='',
                        help='Only re-image this subset of nodes '
                        '(colon separated list)')

    # distro versions to use
    parser.add_argument('--sles', dest='sles_distro', default='sles12sp4',
                        help='The version of SLES to use, e.g. "sles12sp4"')
    parser.add_argument('--rhel', dest='rhel_distro', default='rhel75',
                        help='The version of RHEL to use, e.g. "rhel75"')

    # specific node distro selections
    parser.add_argument('--rhel-nodes', dest='rhel_nodes', default='',
                        help='Configure selected nodes to re-image as RHEL '
                        '(colon separated list)')
    parser.add_argument('--sles-nodes', dest='sles_nodes', default='',
                        help='Configure selected nodes to re-image as SLES '
                        '(colon separated list)')

    # control plane distro selection
    parser.add_argument('--sles-control', action="store_true",
                        help='Configure control nodes to be re-imaged as '
                        'SLES')

    # compute node distro selection
    parser.add_argument('--rhel-compute', action="store_true",
                        help='Configure compute nodes to be re-image as '
                        'RHEL')
    parser.add_argument('--sles-compute', action="store_true",
                        help='Configure compute nodes to be re-image as '
                        'SLES')

    args = parser.parse_args()
    servers = Servers(args.cloud, distro=args.default_distro,
                      distros=dict(sles=args.sles_distro,
                                   rhel=args.rhel_distro))

    if not args.cobble_nodes:
        cobble_nodes = []
    else:
        cobble_nodes = set(args.cobble_nodes.split(':'))

    rhel_node_ids = set(args.rhel_nodes.split(':'))
    sles_node_ids = set(args.sles_nodes.split(':'))

    for server in servers.servers:
        server_distro = None

        if cobble_nodes and server['id'] not in cobble_nodes:
            logger.info("Skipping node '%s' as not in set of nodes to be "
                        "cobbled" % (server['id']))
            continue

        # first check for specific node distro selections
        if server['id'] in sles_node_ids:
            server_distro = 'sles'
        elif server['id'] in rhel_node_ids:
            server_distro = 'rhel'

        if (server_distro is None) and (("COMPUTE" in server['role']) or
                                        ("RESOURCE" in server['role'])):
            # check for blanket all compute setting
            if args.sles_compute:
                server_distro = 'sles'
            elif args.rhel_compute:
                server_distro = 'rhel'

        if (server_distro is None) and ("CONTROLLER" in server['role']):
            # check first for blanket all control setting
            if args.sles_control:
                server_distro = 'sles'

        if server_distro is None:
            server_distro = args.default_distro

        servers.set_distro_id(server, server_distro)

    # write out changes if necessary
    servers.commit()


if __name__ == '__main__':
    main()

# vim:shiftwidth=4:tabstop=4:expandtab
