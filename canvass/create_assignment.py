import argparse
import datetime
import json
import os
import re

import requests
import yaml

def read_token(token_file='token.txt'):
    try:
        with open(token_file) as f:
            return f.read().strip()
    except IOError:
        print('Canvas token file not found:', token_file)

def load_config(config_fname):
    with open(config_fname) as f:
        config_text = f.read()

    # replace !extends <filename> with <filename> contents
    # <filename> is a relative path to the inherited yaml file
    base_dir = os.path.split(config_fname)[0]
    extends_re = re.compile('^!extends\s+(.*)$', re.MULTILINE)
    def extends_repl(matchobj):
        fname = os.path.join(base_dir, matchobj.group(1))
        with open(fname) as f:
            return f.read()

    # handle inheritance
    while re.search(extends_re, config_text):
        config_text = re.sub(extends_re, extends_repl, config_text)

    config = yaml.load(config_text)
    for k, v in config.items():
        if isinstance(v, datetime.datetime):
            config[k] = v.replace(second=0)
    return config

def create_slip_days(config):
    tz_offset = datetime.timedelta(hours=7)

    if 'max_slip_days' not in config:
        config['due_at'] += tz_offset
        return [config]

    max_slip_days = config.pop('max_slip_days')
    assert max_slip_days > 0, 'max_slip_days must be positive'

    slip_day_configs = []
    for slip_day in range(max_slip_days + 1):
        slip_day_config = dict(config)
        slip_day_config['name'] += ' ({} slip day{})'.format(
            slip_day, 's' if slip_day != 1 else '')

        slip_offset = datetime.timedelta(days=slip_day)
        total_offset = tz_offset + slip_offset

        due = slip_day_config['due_at']
        slip_day_config['due_at'] = due + total_offset

        lock = slip_day_config['lock_at']
        slip_day_config['lock_at'] = lock + total_offset

        if slip_day > 0:
            # unlock on due date at midnight
            unlock = due.replace(hour=0, minute=0)
            slip_day_config['unlock_at'] = unlock + total_offset

        slip_day_configs.append(slip_day_config)
    return slip_day_configs

# POST /api/v1/courses/:course_id/assignments
base_url = 'https://bcourses.berkeley.edu/api/v1/courses/{course_id}/assignments'
def upload(config, token):
    headers = {'authorization': 'Bearer ' + token}
    course_id = config['course_id']
    upload_url = base_url.format(course_id=course_id)

    params = {}
    for key, val in config.items():
        if isinstance(val, datetime.datetime):
            val = val.isoformat() + '.000Z'
        new_key = 'assignment[{}]'.format(key)
        if isinstance(val, list):
            new_key += '[]'
        params[new_key] = val

    print(config['name'])
    response = requests.request('POST', upload_url,
                                headers=headers, params=params)
    response.raise_for_status()

def upload_all(configs):
    token = read_token()
    if token is not None:
        for config in configs:
            upload(config, token)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('config')
    args = parser.parse_args()

    config = load_config(args.config)
    to_upload = create_slip_days(config)

    upload_all(to_upload)
