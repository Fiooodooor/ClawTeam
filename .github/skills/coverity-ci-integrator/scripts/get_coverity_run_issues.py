import requests
from requests.auth import HTTPBasicAuth
import json
from past.builtins import xrange
import sys
import os
import argparse

# Please modify the following variables according to your environment.
global cc_server, cc_project, cc_stream, cc_snapshot, cc_user, cc_pass
cc_max_issues = 2000

# Do not Modify this
cc_headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}


def GetIssuesFromSnapshot(snapshot):
    payload = '{"filters": [ { "columnKey": "project","matchMode": "oneOrMoreMatch", "matchers": [ { "class": "Project","name": "' + cc_project + '", "type": "nameMatcher" } ] } ],"snapshotScope":{"show":{"scope":' + snapshot + '}},"columns": ["cid","status","owner","displayImpact","classification","displayType","severity","action","displayComponent","displayCategory","displayFile","displayFunction","legacy","lastDetectedId","lastDetected"]}'

    rp = requests.post(
        cc_server + '/api/v2/issues/search?includeColumnLabels=false&locale=en_us&offset=0&queryType=bysnapshot&rowCount=' + str(
            cc_max_issues) + '&sortOrder=asc', auth=HTTPBasicAuth(cc_user, cc_pass), data=payload, headers=cc_headers)
    issues = rp.json()
    issues = issues["rows"]
    print("Retreiving " + str(len(issues)) + " issues from project:" + cc_project)
    print(
        "cid,status,owner,impact,classification,type,severity,action,component,category,file,function,legacy,last_snapshot,lastDetected")
    for i in xrange(0, len(issues)):
        print(issues[i][0]["value"] + "," + issues[i][1]["value"] + "," + issues[i][2]["value"] + "," + issues[i][3][
            "value"] + "," + issues[i][4]["value"] + "," + issues[i][5]["value"] + "," + issues[i][6]["value"] + "," +
              issues[i][7]["value"] + "," + issues[i][8]["value"] + "," + issues[i][9]["value"] + "," + issues[i][10][
                  "value"] + "," + issues[i][11]["value"] + "," + issues[i][12]["value"] + "," + issues[i][13][
                  "value"] + "," + issues[i][14]["value"])


def main(args):
    try:
        parser = argparse.ArgumentParser(description='Get snapshot defects')
        parser.add_argument('-server', '--cc_server', help='server url', type=str, required=True)
        parser.add_argument('-project', '--cc_project', help='project name', type=str, required=True)
        parser.add_argument('-stream', '--cc_stream', help='stream name', type=str, required=True)
        parser.add_argument('-snapshot', '--cc_snapshot', help='snapshot number', type=str, required=True)
        parser.add_argument('-user', '--cc_user', help='user', type=str, required=True)
        parser.add_argument('-pass', '--cc_pass', help='password', type=str, required=True)

        argv = parser.parse_args(args)

        global cc_server, cc_project, cc_stream, cc_snapshot, cc_user, cc_pass
        cc_server = argv.cc_server
        cc_project = argv.cc_project
        cc_stream = argv.cc_stream
        cc_snapshot = argv.cc_snapshot
        cc_user = argv.cc_user
        cc_pass = argv.cc_pass

        GetIssuesFromSnapshot(cc_snapshot)
        return 0

    except Exception as err:
        print('EXCEPTION: {}'.format(err))
        return -1


if __name__ == '__main__':
    status = main(sys.argv[1:])
    exit(status)
