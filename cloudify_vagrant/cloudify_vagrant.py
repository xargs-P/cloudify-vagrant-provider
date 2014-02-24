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
import shutil
import yaml
import vagrant
import sys
from copy import deepcopy
from jinja2 import Environment, FileSystemLoader
import logging
import logging.config
import config

# Validator
from IPy import IP
from jsonschema import ValidationError, Draft4Validator
from schemas import VAGRANT_SCHEMA


CONFIG_FILE_NAME = 'cloudify-config.yaml'
DEFAULTS_CONFIG_FILE_NAME = 'cloudify-config.defaults.yaml'
VAGRANT_FILE_NAME = 'Vagrantfile.template'
GENERATED_VAGRANT_FILE_NAME = 'Vagrantfile'


#initialize logger
try:
    d = os.path.dirname(config.LOGGER['handlers']['file']['filename'])
    if not os.path.exists(d):
        os.makedirs(d)
    logging.config.dictConfig(config.LOGGER)
    lgr = logging.getLogger('main')
    lgr.setLevel(logging.INFO)
except ValueError:
    sys.exit('could not initialize logger.'
             ' verify your logger config'
             ' and permissions to write to {0}'
             .format(config.LOGGER['handlers']['file']['filename']))


def init(target_directory, reset_config, is_verbose_output=False):
    _set_global_verbosity_level(is_verbose_output)

    if not reset_config and os.path.exists(
            os.path.join(target_directory, CONFIG_FILE_NAME)):
        return False

    provider_dir = os.path.dirname(os.path.realpath(__file__))
    files_path = os.path.join(provider_dir, CONFIG_FILE_NAME)

    lgr.debug('copying provider files from {0} to {1}'
              .format(files_path, target_directory))
    shutil.copy(os.path.join(provider_dir, CONFIG_FILE_NAME),
                target_directory)
    return True


def bootstrap(config_path=None, is_verbose_output=False,
              use_bootstrap_script=True):
    _set_global_verbosity_level(is_verbose_output)

    provider_config = _read_config(config_path)
    # _validate_config(config)
    _generate_vagrant_file(provider_config)

    try:
        lgr.debug('initializing vagrant client')
        v = vagrant.Vagrant()

        if v.status().itervalues().next() != 'running':
            lgr.debug('starting vagrant box in {0}'
                      .format(provider_config['provider']))
            v.up(provider=provider_config['provider'])
    finally:
        if provider_config['delete_vagrantfile_after_bootstrap']:
            lgr.debug('deleting generated vagrantfile')
            os.remove(GENERATED_VAGRANT_FILE_NAME)

    return provider_config['management_ip']


def teardown(management_ip, is_verbose_output=False):
    _set_global_verbosity_level(is_verbose_output)

    lgr.debug('NOT YET IMPLEMENTED')
    raise RuntimeError('NOT YET IMPLEMENTED')


def _set_global_verbosity_level(is_verbose_output=False):
    # we need both lgr.setLevel and the verbose_output parameter
    # since not all output is generated at the logger level.
    # verbose_output can help us control that.
    global verbose_output
    verbose_output = is_verbose_output
    if verbose_output:
        lgr.setLevel(logging.DEBUG)


def _generate_vagrant_file(provider_config):

    lgr.debug('attempting to generate vagrantfile')
    provider_dir = os.path.dirname(os.path.realpath(__file__))

    lgr.debug('loading template environment')
    j2_env = Environment(loader=FileSystemLoader(provider_dir))

    lgr.debug('generating content from vagrantfile template')
    vagrant_file_content = \
        j2_env.get_template(VAGRANT_FILE_NAME).render(provider_config)

    lgr.debug('writing content to vagrantfile')
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

    lgr.debug('reading provider config files')
    with open(config_file_path, 'r') as config_file, \
            open(defaults_config_file_path, 'r') as defaults_config_file:

        lgr.debug('safe loading user config')
        provider_config = yaml.safe_load(config_file.read())

        lgr.debug('safe loading default config')
        defaults_config = yaml.safe_load(defaults_config_file.read())

    lgr.debug('merging configs')
    merged_config = _deep_merge_dictionaries(
        provider_config, defaults_config) \
        if provider_config else defaults_config
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


def _validate_config(config, schema=VAGRANT_SCHEMA):
    verifier = VagrantConfigFileValidator()
    lgr.info('validating provider configuration file...')

    verifier._validate_cidr('management_ip', config['management_ip'])
    verifier._validate_schema(config, schema)


class VagrantConfigFileValidator:

    def _validate_schema(self, config, schema):
        v = Draft4Validator(schema)
        if v.iter_errors(config):
            errors = ';\n'.join('config file validation error found at key:'
                                ' %s, %s' % ('.'.join(e.path), e.message)
                                for e in v.iter_errors(config))
        try:
            v.validate(config)
        except ValidationError:
            lgr.error('{0}'.format(errors))
            sys.exit()

    def _validate_cidr(self, field, cidr):
        try:
            IP(cidr)
        except ValueError as e:
            lgr.error('config file validation error found at key:'
                      ' {0}. {1}'.format(field, e.message))
            sys.exit()
