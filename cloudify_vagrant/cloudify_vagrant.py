########
# Copyright (c) 2013 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#    * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    * See the License for the specific language governing permissions and
#    * limitations under the License.

__author__ = 'ran'

import os
import subprocess
import shutil
import logging
import yaml
import vagrant
from copy import deepcopy
from jinja2 import Environment, FileSystemLoader


CONFIG_FILE_NAME = 'cloudify-config.yaml'
DEFAULTS_CONFIG_FILE_NAME = 'cloudify-config.defaults.yaml'
VAGRANT_FILE_NAME = 'Vagrantfile.template'
GENERATED_VAGRANT_FILE_NAME = 'Vagrantfile'


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def configure(target_directory, reset_config):
    if not reset_config and os.path.exists(
            '{0}/{1}'.format(target_directory, CONFIG_FILE_NAME)):
        return False

    provider_dir = os.path.dirname(os.path.realpath(__file__))
    shutil.copy('{0}/{1}'.format(provider_dir, CONFIG_FILE_NAME),
                target_directory)
    return True


def bootstrap(config_path=None):
    config = _read_config(config_path)
    _generate_vagrant_file(config)
    try:
        v = vagrant.Vagrant()
        if v.status.itervalues().next() != 'running':
            v.up(provider='virtualbox')
    finally:
        os.remove(GENERATED_VAGRANT_FILE_NAME)

    return config['management_ip']


def teardown(management_ip):
    raise RuntimeError('NOT YET IMPLEMENTED')


def _generate_vagrant_file(config):
    provider_dir = os.path.dirname(os.path.realpath(__file__))
    j2_env = Environment(loader=FileSystemLoader(provider_dir))
    vagrant_file_content = \
        j2_env.get_template(VAGRANT_FILE_NAME).render(config)
    with open(GENERATED_VAGRANT_FILE_NAME, 'w') as f:
        f.write(vagrant_file_content)


def _read_config(config_file_path):
    if not config_file_path:
        config_file_path = CONFIG_FILE_NAME
    defaults_config_file_path = os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        DEFAULTS_CONFIG_FILE_NAME)

    if not os.path.exists(config_file_path) or not os.path.exists(
            defaults_config_file_path):
        if not os.path.exists(defaults_config_file_path):
            raise ValueError('Missing the defaults configuration file; '
                             'expected to find it at {0}'.format(
                                 defaults_config_file_path))
        raise ValueError('Missing the configuration file; expected to find '
                         'it at {0}'.format(config_file_path))

    with open(config_file_path, 'r') as config_file, \
            open(defaults_config_file_path, 'r') as defaults_config_file:
        user_config = yaml.safe_load(config_file.read())
        defaults_config = yaml.safe_load(defaults_config_file.read())

    merged_config = _deep_merge_dictionaries(user_config, defaults_config)
    return merged_config


def _deep_merge_dictionaries(overriding_dict, overridden_dict):
    merged_dict = deepcopy(overridden_dict)
    for k, v in overriding_dict.iteritems():
        if k in merged_dict and isinstance(v, dict):
            if isinstance(merged_dict[k], dict):
                merged_dict[k] = _deep_merge_dictionaries(v, merged_dict[k])
            else:
                raise RuntimeError('type conflict at key {0}'.format(k))
        else:
            merged_dict[k] = deepcopy(v)
    return merged_dict
