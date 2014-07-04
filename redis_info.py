# redis-collectd-plugin - redis_info.py
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; only version 2 of the License is applicable.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin St, Fifth Floor, Boston, MA  02110-1301 USA
#
# Authors:
#   Garret Heaton <powdahound at gmail.com>
#
# About this plugin:
#   This plugin uses collectd's Python plugin to record Redis information.
#
# collectd:
#   http://collectd.org
# Redis:
#   http://redis.googlecode.com
# collectd-python:
#   http://collectd.org/documentation/manpages/collectd-python.5.shtml

import collectd
import redis


# Verbose logging on/off. Override in config by specifying 'Verbose'.
VERBOSE_LOGGING = False

REDIS_NODES = dict()

def fetch_info(node):
    """Connect to Redis server and request info"""
    c = redis.Redis(connection_pool=node['pool'])
    return c.info()

def parse_info(info_lines):
    """Parse info response from Redis"""
    info = {}
    for line in info_lines:
        if "" == line or line.startswith('#'):
            continue

        if ':' not in line:
            collectd.warning('redis_info plugin: Bad format for info line: %s'
                             % line)
            continue

        key, val = line.split(':')

        # Handle multi-value keys (for dbs).
        # db lines look like "db0:keys=10,expire=0"
        if ',' in val:
            split_val = val.split(',')
            val = {}
            for sub_val in split_val:
                k, _, v = sub_val.rpartition('=')
                val[k] = v

        info[key] = val
    info["changes_since_last_save"] = info.get("changes_since_last_save", info.get("rdb_changes_since_last_save"))
    return info


def configure_callback(conf):
    """Receive configuration block"""
    global VERBOSE_LOGGING, REDIS_NODES
    for node in conf.children:
        if node.key == 'Node':
            new_node = {'host': 'localhost', 'port': 6379}
            REDIS_NODES[node.values[0]] = new_node
            for param in node.children:
                if param.key == 'Host': new_node['host'] = param.values[0]
                if param.key == 'Port': new_node['port'] = int(param.values[0])
                if param.key == 'Password': new_node['password'] = param.values[0]
            new_node['pool'] = redis.ConnectionPool(host=new_node['host'], port=new_node['port'])
            log_verbose('Configured with host=%s, port=%s' % (new_node['host'], new_node['port']))
        elif node.key == 'Verbose':
            VERBOSE_LOGGING = bool(node.values[0])
        else:
            collectd.warning('redis_info plugin: Unknown config key: %s.'
                             % node.key)


def dispatch_value(info, node, key, type, type_instance=None):
    """Read a key from info response data and dispatch a value"""
    if key not in info:
        collectd.warning('redis_info plugin: Info key not found: %s' % key)
        return

    if not type_instance:
        type_instance = key

    value = int(info[key])
    log_verbose('Sending value: %s=%s' % (type_instance, value))

    val = collectd.Values(plugin='redis_info')
    val.plugin_instance = node
    val.type = type
    val.type_instance = type_instance
    val.values = [value]
    val.dispatch()


def read_callback():
    log_verbose('Read callback called')
    for node_name, node in REDIS_NODES.iteritems():
        info = fetch_info(node)

        if not info:
            collectd.error('redis plugin: No info received')
            return
        # send high-level values
        dispatch_value(info, node_name, 'uptime_in_seconds','gauge')
        dispatch_value(info, node_name, 'connected_clients', 'gauge')
        dispatch_value(info, node_name, 'connected_slaves', 'gauge')
        dispatch_value(info, node_name, 'blocked_clients', 'gauge')
        dispatch_value(info, node_name, 'evicted_keys', 'gauge')
        dispatch_value(info, node_name, 'used_memory', 'bytes')
        dispatch_value(info, node_name, 'changes_since_last_save', 'gauge')
        dispatch_value(info, node_name, 'total_connections_received', 'counter',
                       'connections_received')
        dispatch_value(info, node_name, 'total_commands_processed', 'counter',
                       'commands_processed')

        # database and vm stats
        for key in info:
            if key.startswith('vm_stats_'):
                dispatch_value(info, node_name, key, 'gauge')
            if key.startswith('db'):
                dispatch_value(info[key], node_name, 'keys', 'gauge', '%s-keys' % key)


def log_verbose(msg):
    if not VERBOSE_LOGGING:
        return
    collectd.info('redis plugin [verbose]: %s' % msg)


# register callbacks
collectd.register_config(configure_callback)
collectd.register_read(read_callback)
