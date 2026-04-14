#!/usr/bin/env python
"""
* ============================================================================
* COPYRIGHT
* INTEL CONFIDENTIAL
*
* Copyright (c) 2018 Intel Corporation
* Copyright (c) 2017-2018 Intel Corporation All Rights Reserved.
*
* The source code contained or described herein and all documents related to
* the source code ("Material") are owned by Intel Corporation or its
* suppliers or licensors.
*
* Title to the Material remains with Intel Corporation or its suppliers and
* licensors. The Material contains trade secrets and proprietary and
* confidential information of Intel or its suppliers and licensors.
* The Material is protected by worldwide copyright and trade secret laws and
* treaty provisions. No part of the Material may be used, copied, reproduced,
* modified, published, uploaded, posted, transmitted, distributed,
* or disclosed in any way without Intel's prior express written permission.
*
* No license under any patent, copyright, trade secret or other intellectual
* property right is granted to or conferred upon you by disclosure
* or delivery of the Materials, either expressly, by implication, inducement,
* estoppel or otherwise. Any license under such intellectual property rights
* must be express and approved by Intel in writing.
*
* = PRODUCT
*
*
* = FILENAME
*      create_coverity_report.py
*
* = DESCRIPTION
*      Module for Parsing KW XML report results or pulling from KW server and creating HTML report which will be sent by mail
*
* = AUTHOR
*      Alex Bilik
*
* = CREATION DATE
*      APR 1, 2023
* ============================================================================
"""

from os.path import isfile, dirname, abspath, join, basename, isdir
import glob
import csv
import re
import argparse
from json import loads, load
import sys
import requests
import urllib.parse
import itertools
from requests.auth import HTTPBasicAuth
from collections import namedtuple
ABS_SCRIPT_PATH = dirname(abspath(__file__))
sys.path.append(dirname(ABS_SCRIPT_PATH))
sys.path.append(dirname(dirname(ABS_SCRIPT_PATH)))
from pyTools.CCT.HTMLBuilder import HTMLBuilder
from pyTools.CCT.Mailer import Mailer
try:
    from CCT.Plotter import Plotter
    g_pyplot_enabled = True
except Exception as e:
    g_pyplot_enabled = False
requests.packages.urllib3.disable_warnings()

BUILD_PROBLEMS = namedtuple('BUILD_PROBLEMS', ['PROJECT','STREAM', 'PROJECT_LINK', 'OWNER_MAIL', 'BUILD_NAME', 'SNAPSHOT', 'ERROR_EXISTS', 'PROBLEMS'])
XML_PROBLEM = namedtuple('XML_PROBLEM', ['PROBLEM_ID', 'FILE', 'LINE', 'FUNCTION', 'CODE', 'MESSAGE', 'SEVERITY', 'SEVERITY_LEVEL'])
WEB_PROBLEM = namedtuple('WEB_PROBLEM',
                         ['ID', 'URL', 'TITLE', 'FILE', 'LINE', 'FUNCTION', 'MESSAGE', 'SEVERITY', 'IMPACT', 'IMPACT_CODE',
                          'STATE', 'STATUS', 'CHECKER', 'OWNER'])
PROJECT_LINK_OWNER = namedtuple('PROJECT_LINK_OWNER', ['PROJECT_LINK', 'OWNER'])
HTML_REPORT_FILE = 'Coverity_report.html'
FW_CI_EMAIL = 'sys_sysfw@intel.com'
MANUAL_BUILD_REASON = 'Manual'
MAX_ISSUES=2000

COVERITY_PROJECT_LINK_OWNER_MAP = {"IMC_NVM_GENERATOR":PROJECT_LINK_OWNER(PROJECT_LINK="https://coverity.devtools.intel.com/prod8/reports.htm#v28237/p11754",OWNER="olesya.sharify@intel.com"),
                            "IMC_BOOT":PROJECT_LINK_OWNER(PROJECT_LINK="https://coverity.devtools.intel.com/prod8/reports.htm#v28237/p11753",OWNER="dor.itah@intel.com"),
                            "IMC_UBOOT":PROJECT_LINK_OWNER(PROJECT_LINK="https://coverity.devtools.intel.com/prod8/reports.htm#v28237/p11749",OWNER="dor.itah@intel.com"),
                            "IMC_USERSPACE":PROJECT_LINK_OWNER(PROJECT_LINK="https://coverity.devtools.intel.com/prod8/reports.htm#v28237/p11767",OWNER="sharon.haroni@intel.com"),
                            "IMC_PHYSS":PROJECT_LINK_OWNER(PROJECT_LINK="https://coverity.devtools.intel.com/prod8/reports.htm#v23256/p11765",OWNER="alex.koshevarov@intel.com"),
                            "IMC_INFRA":PROJECT_LINK_OWNER(PROJECT_LINK="https://coverity.devtools.intel.com/prod8/reports.htm#v28237/p11766",OWNER="dor.itah@intel.com"),
                            "IMC_NSL":PROJECT_LINK_OWNER(PROJECT_LINK="https://coverity.devtools.intel.com/prod8/reports.htm#v28237/p11745",OWNER="nizan.zorea@intel.com"),
                            "IMC_XT_COMMON":PROJECT_LINK_OWNER(PROJECT_LINK="https://coverity.devtools.intel.com/prod8/reports.htm#v28237/p11752",OWNER="alex.koshevarov@intel.com"),
                            "IMC_SEP":PROJECT_LINK_OWNER(PROJECT_LINK="https://coverity.devtools.intel.com/prod8/reports.htm#v27237/p11751",OWNER="israel.davidenko@intel.com"),
                            "IMC_HIFMC":PROJECT_LINK_OWNER(PROJECT_LINK="https://coverity.devtools.intel.com/prod8/reports.htm#v27237/p11744",OWNER="shay.amir@intel.com"),
                            "IMC_ATF":PROJECT_LINK_OWNER(PROJECT_LINK="https://coverity.devtools.intel.com/prod8/reports.htm#v23256/p11757",OWNER="dor.itah@intel.com")}

IMPACT_CODES = {'Critical':1,
                'High':2,
                'Medium':3,
                'Low':4}


def get_project_link_and_owner(project_name, server_name):
    if project_name in COVERITY_PROJECT_LINK_OWNER_MAP:
        if server_name in COVERITY_PROJECT_LINK_OWNER_MAP[project_name].PROJECT_LINK:
            return COVERITY_PROJECT_LINK_OWNER_MAP[project_name].PROJECT_LINK, COVERITY_PROJECT_LINK_OWNER_MAP[project_name].OWNER
    return '', ''


def get_unique_problem_statuses_count_dict(problems):
    unique_problem_statuses = dict()

    all_statuses = set([s.STATUS for s in problems])

    for status in all_statuses:
        unique_problem_statuses[status] = len([s for s in problems if s.STATUS == status])

    return unique_problem_statuses


def create_html_report(build_problems_from_coverity_server, html_output_file, build_name,
                       branch_name, build_url, coverity_server, build_user, force_display_queries):
    html_builder = HTMLBuilder(out_file=html_output_file)

    attached_diagrams_list = []
    owner_mails_to_send = []
    html_builder.add_centered_bold_headline('Coverity Issues report')
    html_builder.add_empty_space()
    html_builder.add_plain_html(html="""
    <style type="text/css">
                    .link-text {
                        color: blue;
                        font-size: 13px;
                    }
                    .kw-issue-list-small {
                        font-size: 11px;
                        line-height: 15px;
                    }
                    .kw-issue-list-gray { color: #454545; }
                    .kw-issue-list-table {
                        width: 100%;                        
                        border-collapse: collapse;
                        border: 1px solid #CCC;
                    }
                    .even { background: white; }
                    .odd { background: #CCC; }
                </style></head>""")

    # Add requesting user name
    html_builder.add_strong_with_soft_line(strong_txt='Requested for:',
                                           soft_txt=build_user,
                                           color_strong=html_builder.COLOR_GREEN)
    # Add branch name
    html_builder.add_strong_with_soft_line(strong_txt='Branch Name:',
                                           soft_txt=branch_name,
                                           color_strong=html_builder.COLOR_GREEN)
    # Print reason for manual triggered builds
    if force_display_queries:
        html_builder.add_strong_with_soft_line(strong_txt='Build Reason:',
                                               soft_txt='Manual report',
                                               color_strong=html_builder.COLOR_GREEN)
    # Add KW server build URLs or build names
    if not build_problems_from_coverity_server:
        html_builder.add_strong_with_soft_line(strong_txt='Build Name:',
                                               soft_txt=build_name,
                                               color_strong=HTMLBuilder.COLOR_GREEN)

    html_builder.add_empty_space()
    html_builder.add_link_with_txt(text_before='Jenkins Build ', link_text='URL', link=build_url, text_after='')
    html_builder.add_empty_space()

    for project_problems in build_problems_from_coverity_server:
        # The following variable will be used in case of a Manual triggered build to show the report without the tables and charts (for zero issues)
        found_zero_problems = False
        # If no errors found, can proceed, unless it's a manually triggered build...
        if len(project_problems.PROBLEMS) == 0:
            found_zero_problems = True
            if not force_display_queries:
                continue
        if project_problems.OWNER_MAIL:
            if project_problems.OWNER_MAIL not in owner_mails_to_send:
                owner_mails_to_send.append(project_problems.OWNER_MAIL)
        html_builder.add_strong_with_soft_line(
            strong_txt='New and Existing problems detected for {} project:'.format(project_problems.STREAM), soft_txt=len(project_problems.PROBLEMS))
        problem_list = project_problems.PROBLEMS  # Assuming project_problems.PROBLEMS is the list of problems

        cids_html_query_parts = []
        cids_html_query_part = ""
        for i, problem in enumerate(problem_list):
            cids_html_query_part += "&cid=" + str(problem.ID)
            if (i + 1) % 100 == 0:
                cids_html_query_parts.append(cids_html_query_part)
                cids_html_query_part = ""
        if cids_html_query_part:
            cids_html_query_parts.append(cids_html_query_part)
        for query_part in cids_html_query_parts:
            print(query_part)
            cids = query_part.split("&cid=")
            first_cid = cids[1]  # First CID (problem ID)
            last_cid = cids[-1]  # Last CID (problem ID)
            probs_link = f'{coverity_server}/query/defects.htm?project={project_problems.PROJECT}&snapshotId={project_problems.SNAPSHOT}{query_part}'
        # Adding Coverity project link
            html_builder.add_link_with_txt(text_before=f'Coverity project issues {first_cid}-{last_cid} URL: ',
                                        link_text='{}-{}-cids-{}-{}'.format(project_problems.STREAM,
                                                                 project_problems.BUILD_NAME,
                                                                 first_cid,
                                                                 last_cid),
                                        link=probs_link,
                                        text_after='')
        if not found_zero_problems:
            # Getting all unique problems and their count
            problem_types_count_dict = get_unique_problem_statuses_count_dict(project_problems.PROBLEMS)
            # Placing all unique problems and their count in a table
            html_builder.add_plain_html("<table border=1>")
            for i, val in enumerate(problem_types_count_dict):
                html_builder.add_plain_html("<tr><td>{}</td><td>{}</td></tr>".format(val.replace("_", " ").capitalize(), problem_types_count_dict[val]))
            html_builder.add_plain_html("</table>")
            # Creating plotter class to plot pie chart
            try:
                if g_pyplot_enabled:
                    plotter = Plotter()
                    pie_chart_file_path = join(dirname(html_output_file), '{}_{}_{}.png'.format(project_problems.BUILD_NAME, project_problems.STREAM, project_problems.SNAPSHOT))
                    plotter.pie_chart(labels=list(problem_types_count_dict.keys()), sizes=list(problem_types_count_dict.values()),
                                      pie_chart_file_path=pie_chart_file_path, shadow=False)
                    # Adding picture diagram to html file
                    html_builder.add_picture_diagram_list(diagrams_path_list=[pie_chart_file_path], width=450, height=350)
                    # Adding pie chart file to be returned and attached to the mail
                    attached_diagrams_list.append(pie_chart_file_path)
            except Exception as e:
                print ('Got exception when trying to create pie chart: {}'.format(e))

            # Placing all found issues in a tble with alternating color - grey/white
            html_builder.add_plain_html("<table cellspacing=\"0\" cellpadding=\"2\" class=\"kw-issue-list-table\">")
            for num, problem in enumerate(sorted(project_problems.PROBLEMS, key=lambda k: k.IMPACT_CODE), 1):
                even = "even" if (num % 2) else "odd"
                html_builder.add_plain_html("<td class=\"{}\"><div>#{}: <span class=\"link-text\"><a href={}>{}</a></span></div><div class=\"kw-issue-list-small kw-issue-list-gray\"> \
                        <span>{}</span> | {} | {}</div><div class=\"kw-issue-list-small kw-issue-list-gray\">Checker: {} | Impact: {} | Severity: {} | State: {} | Status: {} | \
                        Message: {}</div></td></tr>".format(even,
                                                            problem.ID,
                                                            problem.URL,
                                                            problem.TITLE,
                                                            problem.FILE,
                                                            problem.FUNCTION,
                                                            problem.LINE,
                                                            problem.CHECKER,
                                                            problem.IMPACT,
                                                            problem.SEVERITY,
                                                            problem.STATE,
                                                            problem.STATUS,
                                                            problem.MESSAGE))
            html_builder.add_plain_html("</table></body></html>")

        html_builder.add_empty_space()

    return html_builder.finish_html(), attached_diagrams_list, owner_mails_to_send


def get_klocwork_builds(username, login_token, kw_project, kw_server):
    """ Function to retrieve issues for build from KW """
    data = {
        'user': username,
        'ltoken': login_token,
        'project': kw_project,
        'action': 'builds'
    }
    url = "{}/review/api".format(kw_server)
    res = requests.post(url, data=data, verify=False)
    builds = res.text
    # print (issues)
    return [loads(build) for build in builds.split('\n') if build]


def get_kw_issue_details(issue_id, username, login_token, kw_project, kw_server):
    """ Function to retrieve issue details """
    data = {
        'user': username,
        'ltoken': login_token,
        'project': kw_project,
        'action': 'issue_details',
        'id': issue_id
    }
    url = "{}/review/api".format(kw_server)
    res = requests.post(url, data=data, verify=False)
    print(res.text)
    return res.text


def get_key_value_dict(issue):
    return {s['key']:s['value'] for s in issue}


def get_coverity_issues_for_snapshot(project_name, snapshot, username, login_token, coverity_server, use_proxy=False):
    if use_proxy:
        proxies = {
            'http': 'http://proxy-chain.intel.com:911',
            'https': 'http://proxy-chain.intel.com:911'
        }
    else:
        proxies = None

    headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
    payload = '{{"filters": [ {{ "columnKey": "project", "matchMode": "oneOrMoreMatch", "matchers": [ {{ "class": "Project","name": "{project_name}", "type": "nameMatcher" }} ] }} ],"snapshotScope":{{"show":{{"scope":{snapshot}}}}},"columns": ["cid","status","owner","impact","checker","displayImpact","classification","displayType","severity","action","displayComponent","displayCategory","displayFile","displayFunction","legacy","lastDetectedId","lastDetected","lineNumber"]}}'.format(project_name=project_name, snapshot=snapshot)

    request = f'{coverity_server}/api/v2/issues/search?includeColumnLabels=false' \
              f'&locale=en_us&offset=0&queryType=bysnapshot&rowCount={MAX_ISSUES}&sortOrder=asc'
    print(f'headers:\n{headers}')
    print(f'Payload:\n{payload}')
    print(f'Request:\n{request}')

    rp = requests.post(request, auth=HTTPBasicAuth(username, login_token), data=payload, headers=headers, proxies=proxies)
    assert rp.status_code == 200, f'Query for {project_name} and snapshot:{snapshot} ended with error code: {rp.status_code} with reason: {rp.reason}'
    issues = rp.json()
    return issues["rows"]


def set_impact_code(impact):
    if impact in IMPACT_CODES:
        return IMPACT_CODES[impact]
    else:
        return 0

def get_json_from_json_file(json_file):
    # Open the JSON file
    with open(json_file) as file:
        # Load the contents of the file
        data = load(file)
        return data

def get_coverity_issues_from_web_api_or_jsons(project_names, stream_names, coverity_user, results_path, coverity_token, coverity_server, build_name, jsons_path, use_proxy=False):
    build_problems_from_coverity_server = []
    snapshot_stream_error = False

    # Get all snapshot files
    assert isdir(results_path), f'Results path dir not found: {results_path}'
    snapshots_file_list = glob.glob(join(results_path, 'snapshot-*.txt'))
    assert snapshots_file_list, f'Could not find any snapshot files at: {results_path}'

    if jsons_path:
        results_file_list = glob.glob(join(jsons_path, 'results-*.json'))
        assert results_file_list, f'Could not find any results files at: {jsons_path}'
    for project_name, stream_name in zip(project_names, stream_names or itertools.repeat(None)):
        project_link, owner_mail = get_project_link_and_owner(project_name, coverity_server)
        snapshot_file = next((s for s in snapshots_file_list if stream_name in basename(s)), None)
        if not snapshot_file:
            print(f'WARNING: Snapshot file for stream: {stream_name} is missing!! Creating report without it')
            snapshot_stream_error = True
            build_problems_from_coverity_server.append(BUILD_PROBLEMS(PROJECT=project_name,
                                                                      STREAM=stream_name,
                                                                      PROJECT_LINK=project_link,
                                                                      OWNER_MAIL=owner_mail,
                                                                      BUILD_NAME=build_name,
                                                                      SNAPSHOT='',
                                                                      ERROR_EXISTS=f'Snapshot file for stream: {stream_name} is missing!!',
                                                                      PROBLEMS=[]))
            continue

        with open(snapshot_file, 'r') as snapshot_file_in:
            snapshot_id = snapshot_file_in.readline().strip()

        try:
            if jsons_path:
                jsonfile = next((s for s in results_file_list if stream_name in basename(s)), None)
                print(f"taken info from json file {jsonfile}")
                coverity_issues = get_json_from_json_file(json_file=jsonfile)
            else:
                print("taken info from server")
                coverity_issues = get_coverity_issues_for_snapshot(project_name=project_name,
                                                               snapshot=snapshot_id,
                                                               username=coverity_user,
                                                               login_token=coverity_token,
                                                               coverity_server=coverity_server)
        except Exception as e:
            print(f'WARNING: query for {stream_name} failed with exception: {e}')
            snapshot_stream_error = True
            build_problems_from_coverity_server.append(BUILD_PROBLEMS(PROJECT=project_name,
                                                                      STREAM=stream_name,
                                                                      PROJECT_LINK=project_link,
                                                                      OWNER_MAIL=owner_mail,
                                                                      BUILD_NAME=build_name,
                                                                      SNAPSHOT=snapshot_id,
                                                                      ERROR_EXISTS=f'Query for {stream_name} failed with exception: {e}',
                                                                      PROBLEMS=[]))
            continue

        problems_list = []

        if coverity_issues:
            print(f'\nFound issues for stream: {stream_name} snapshotID: {snapshot_id}')
        for i, element in enumerate(coverity_issues, 1):
            # print(i)
            if not element:
                continue
            issue = get_key_value_dict(element)
            # Skip issues if status is not New
            if issue['status'].lower() != 'new':
                print('Found an issue in status: {}, skipping...'.format(issue['status']))
                continue

            if re.findall('sources(.*)', issue['displayFile']):
                file_path = re.findall('sources(.*)', issue['displayFile'])[0]
            else:
                file_path = issue['displayFile']


            print('-->Found issue Category: {} status: {} impact: {} severity: {} action: {}\nfile: {} function: {} line: {} message: {} checker: {} owner: {}'.
                  format(issue['displayCategory'],
                         issue['status'],
                         issue['displayImpact'],
                         issue['severity'],
                         issue['action'],
                         file_path,
                         issue['displayFunction'],
                         issue['lineNumber'],
                         issue['displayType'],
                         issue['checker'],
                         issue['owner']))
            encoded_project_name = urllib.parse.quote(project_name)
            problem_url = f'{coverity_server}/query/defects.htm?project={encoded_project_name}&snapshotId={snapshot_id}&cid={issue["cid"]}'
            problems_list.append(WEB_PROBLEM(ID=issue['cid'],
                                             URL=problem_url,
                                             TITLE=issue['displayCategory'],
                                             FILE=file_path,
                                             LINE=issue['lineNumber'],
                                             FUNCTION=issue['displayFunction'],
                                             MESSAGE=issue['displayType'],
                                             SEVERITY=issue['severity'],
                                             IMPACT=issue['displayImpact'],
                                             IMPACT_CODE=set_impact_code(issue['displayImpact']),
                                             CHECKER=issue['checker'],
                                             OWNER=issue['owner'],
                                             STATE=issue['action'],
                                             STATUS=issue['status']))

        # TODO: Create and save results in CSV file in results_path

        build_problems_from_coverity_server.append(BUILD_PROBLEMS(PROJECT=project_name,
                                                                  STREAM=stream_name,
                                                                  PROJECT_LINK=project_link,
                                                                  OWNER_MAIL=owner_mail,
                                                                  BUILD_NAME=build_name,
                                                                  SNAPSHOT=snapshot_id,
                                                                  ERROR_EXISTS=None,
                                                                  PROBLEMS=problems_list))

    return build_problems_from_coverity_server, snapshot_stream_error


def main(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("-pn", "--project_names", help="Coverity Project names", required=True, nargs='+', type=str)
    parser.add_argument("-sn", "--stream_names", help="Coverity Stream names", required=True, nargs='+', type=str)
    parser.add_argument("-jsonf", "--json_files_path", help="Coverity json results path, should be send in order of projects/streams", required=False)
    parser.add_argument("-rp", "--results_path", help="Path to folder containing all stream snapshot files and output path for CSV result files", required=True)
    parser.add_argument("-prbr", "--pr_branch_name", help="Pull request branch name", default='')
    parser.add_argument("-bn", "--build_name", help="Coverity Build pipeline name", required=True, default='')
    parser.add_argument("-bu", "--build_url", help="Coverity Build pipeline URL", required=True, default='')
    parser.add_argument("-html", "--html_output_file", help="HTML output file path", required=True)
    parser.add_argument('-at', "--attach_files", help="Attach coverity scan results to the report mail", action="store_true")
    parser.add_argument('-use_proxy', help="Use proxy to query for issues", action="store_true")
    parser.add_argument("-m", "--email_addresses", help="Recipients email addresses, space separated "
                                                        "optional for sending html over mail)", nargs='+', type=str)
    parser.add_argument('-reason', '--build_reason', help="The reason of the build", default='CI')
    parser.add_argument('-us', '--build_user', help="The user name for which the build was triggered for", default='')
    parser.add_argument('-sa', '--use_smtpauth', help="Use SMTPAUTH for sending email messages with authentication "
                                                      "(requires username and password)", action="store_true")
    parser.add_argument('-u', '--username', help="Username for smtpauth mail")
    parser.add_argument('-p', '--password', help="Password for smtpauth mail")
    parser.add_argument('-cu', '--coverity_user', help="User for Coverity API", required=True)
    parser.add_argument('-ct', '--coverity_token', help="Token for Coverity API", required=True)
    parser.add_argument('-cs', '--coverity_server', help="Coverity server", required=True)
    argv = parser.parse_args(args)

    print('Build reason: {}'.format(argv.build_reason))
    if argv.build_reason == MANUAL_BUILD_REASON:
        force_display_queries = True
    else:
        force_display_queries = False

    # Remove empty entries from project_names and stream names
    project_names = list(filter(None, argv.project_names))
    stream_names = list(filter(None, argv.stream_names))
    # Check that there is matching number of projects and build names
    assert len(project_names) == len(stream_names), \
        'Project names should be the same length as the stream names and the same order!'

    # if not check_kw_project_builds_exist(build_names=argv.build_names,
    #                                      username=argv.username,
    #                                      login_token=argv.login_token,
    #                                      kw_projects=argv.project_names,
    #                                      kw_server=argv.kw_server):
    #     exit(1)

    build_problems_from_coverity_server, snapshot_stream_error = get_coverity_issues_from_web_api_or_jsons(
                                                                     project_names=project_names,
                                                                     stream_names=stream_names,
                                                                     coverity_user=argv.coverity_user,
                                                                     coverity_token=argv.coverity_token,
                                                                     results_path=argv.results_path,
                                                                     coverity_server=argv.coverity_server,
                                                                     build_name=argv.build_name,
                                                                     jsons_path=argv.json_files_path,
                                                                     use_proxy=argv.use_proxy)

    # Count number of detected errors
    number_of_problems = sum([len(proj.PROBLEMS) for proj in build_problems_from_coverity_server])
    # If no errors found, finish here and don't sent report
    if number_of_problems == 0:
        if not force_display_queries:
            if not snapshot_stream_error:
                print('Found 0 problems, not creating Coverity html report...')
                exit(0)
            else:
                print('ERROR: Found errors in getting Coverity issues...')
                exit(1)


    for proj in build_problems_from_coverity_server:
        print('Found {} problems for project: {} project_link: {} owner: {}'.
              format(len(proj.PROBLEMS), proj.STREAM, proj.PROJECT_LINK, proj.OWNER_MAIL))

    # Create HTML report when number of errors > 0
    html, attached_diagrams_list, list_of_owner_addresses = create_html_report(build_problems_from_coverity_server, argv.html_output_file,
                                                      argv.build_name, argv.pr_branch_name, argv.build_url, coverity_server=argv.coverity_server,
                                                      build_user=argv.build_user, force_display_queries=force_display_queries)

    # If Email addresses set and not empty, send the HTML report over mail
    email_addresses_list = list_of_owner_addresses + argv.email_addresses
    if email_addresses_list:
        mailer = Mailer(from_add=FW_CI_EMAIL, to_add=email_addresses_list, use_smtpauth=argv.use_smtpauth,
                                   smtpauth_username=argv.username, smtpauth_password=argv.password)
        # TODO: Add result CSV file attachments to report
        senderrs = mailer.send_mail(from_mail = mailer.from_address,
                                    to_mail_list = mailer.to_addresses,
                                    subject='Coverity Report({}) - {}'.format(argv.build_reason, argv.build_name),
                                    html_content = html,
                                    # attached_files_list = argv.attached_files,
                                    embedded_image_list=attached_diagrams_list)
        if senderrs:
            print ('Errors during mail send: {}'.format(senderrs))

    # Exit with the found number of problems
    exit(number_of_problems)


if __name__ == '__main__':
    main(sys.argv[1:])


# -cu
# abilik
# -ct
# 9479F4F52C869889E7B8976156698C7D