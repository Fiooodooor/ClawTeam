#!/usr/bin/env python

import os
import sys
from typing import Union
import requests
import time


def kw_query(data):
    username = str(sys.argv[1])
    login_token = str(sys.argv[2])
    kw_project = str(sys.argv[3])
    kw_server = str(sys.argv[4])
    # Use a CA bundle path if provided, otherwise keep TLS verification enabled.
    # Set KW_CA_BUNDLE to an internal CA PEM file, or KW_TLS_VERIFY=false to
    # explicitly disable verification (insecure; only for trusted private networks).
    ca_bundle = os.environ.get("KW_CA_BUNDLE")
    tls_verify: Union[str, bool] = ca_bundle if ca_bundle else (os.environ.get("KW_TLS_VERIFY", "true").lower() != "false")
    num_of_issues = 0
    for x in range(1, 6):
        print(f'try {x} of 5')
        data = {
            'user': username,
            'ltoken': login_token,
            'project': kw_project,
            'action': 'search', 'query': 'status:Analyze severity:1,2,3,4'
        }
        url = "{}/review/api".format(kw_server)
        res = requests.post(url, data=data, verify=tls_verify)
        issues = str(res.text)
        num_of_issues = issues.count('{"id":')
        print ("number of issues is :" + str(num_of_issues))
        if num_of_issues == 0:
            break
        time.sleep(30)

    sys.exit(num_of_issues)


if __name__ == '__main__':
    kw_query(sys.argv)
