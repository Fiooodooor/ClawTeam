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
*      parse_create_kw_report.py
*
* = DESCRIPTION
*      Module for Parsing KW XML report results or pulling from KW server and creating HTML report which will be sent by mail
*
* = AUTHOR
*      Alex Bilik
*
* = CREATION DATE
*      APR 1, 2020
* ============================================================================
"""

from os.path import isfile, dirname, abspath, join
from xml.dom import minidom
import argparse
from json import loads
import sys
import requests
from collections import namedtuple
ABS_SCRIPT_PATH = dirname(abspath(__file__))
sys.path.append(dirname(ABS_SCRIPT_PATH))
from pyTools.CCT.HTMLBuilder import HTMLBuilder
from pyTools.CCT.Mailer import Mailer
from pyTools.CCT.Plotter import Plotter
requests.packages.urllib3.disable_warnings()

BUILD_PROBLEMS = namedtuple('BUILD_PROBLEMS', ['PROJECT', 'PROJECT_LINK', 'BUILD_NAME', 'QUERY', 'PROBLEMS'])
XML_PROBLEM = namedtuple('XML_PROBLEM', ['PROBLEM_ID', 'FILE', 'LINE', 'FUNCTION', 'CODE', 'MESSAGE', 'SEVERITY', 'SEVERITY_LEVEL'])
WEB_PROBLEM = namedtuple('WEB_PROBLEM',
                         ['ID', 'URL', 'TITLE', 'FILE', 'LINE', 'FUNCTION', 'CODE', 'MESSAGE', 'SEVERITY',
                          'SEVERITY_CODE', 'STATE', 'STATUS'])
HTML_REPORT_FILE = 'KlocWork_report.html'
FW_CI_EMAIL = 'eth.fw.ci@intel.com'
MANUAL_BUILD_REASON = 'Manual'

# QUERY_PARAM_NEW_ISSUES = 'state:New status:+\'Analyze\',+\'Ignore\',+\'Fix\',+\'Fix in Next Release\',+\'Fix in Later Release\',+\'Defer\',+\'Filter\''
# QUERY_PARAM_EXISTING_ISSUES = 'state:Existing status:+\'Analyze\',+\'Ignore\',+\'Fix\',+\'Fix in Later Release\',+\'Defer\''

# QUERY_PARAM_NO_FILTER_ISSUES = 'state:New,Existing status:+\'Analyze\',+\'Ignore\',+\'Fix\',+\'Fix in Next Release\',+\'Fix in Later Release\',+\'Defer\''
QUERY_PARAM_NO_FILTER_NEXT_RELEASE_ISSUES = 'state:New,Existing status:+\'Analyze\',+\'Ignore\',+\'Fix\',+\'Fix in Later Release\',+\'Defer\''
# Query reason: Due to addition of a checker, a lot of issues came up in CVL project with status status 'Fix in Next Release' and code 'Metrics'
QUERY_PARAM_NEXT_RELEASE_NO_METRICS_ISSUES = 'state:New,Existing status:+\'Fix in Next Release\' -code:Metrics'
QUERY_PARAM_FILTER_NO_MISRA_ISSUES = 'state:New,Existing status:+\'Filter\' -code:misra'
MEV_QUERY_PARAM_ISSUES = 'status:+\'Analyze\' severity:1,2,3,4'


def get_unique_problem_statuses_count_dict(problems):
    unique_problem_statuses = dict()

    all_statuses = set([s.STATUS for s in problems])

    for status in all_statuses:
        unique_problem_statuses[status] = len([s for s in problems if s.STATUS == status])

    return unique_problem_statuses


def create_html_report(build_problems_from_kw_server, html_output_file, build_names,
                       branch_name, build_url, pr_url, kw_server, build_user, force_display_queries):
    html_builder = HTMLBuilder(out_file=html_output_file)

    attached_diagrams_list = []
    html_builder.add_centered_bold_headline('KlocWork Errors report')
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
    html_builder.add_strong_with_soft_line(strong_txt='Topic Name:',
                                           soft_txt=branch_name,
                                           color_strong=html_builder.COLOR_GREEN)
    # Print reason for manual triggered builds
    if force_display_queries:
        html_builder.add_strong_with_soft_line(strong_txt='Build Reason:',
                                               soft_txt='Manual report',
                                               color_strong=html_builder.COLOR_GREEN)
    # Add KW server build URLs or build names
    if not build_problems_from_kw_server:
        html_builder.add_strong_with_soft_line(strong_txt='Build Names:',
                                               soft_txt='/'.join(build_names),
                                               color_strong=HTMLBuilder.COLOR_GREEN)

    html_builder.add_empty_space()
    html_builder.add_link_with_txt(text_before='Jenkins Build ', link_text='URL', link=build_url, text_after='')
    # html_builder.add_link_with_txt(text_before='Pull Request ', link_text='URL', link=pr_url, text_after='')
    # html_builder.add_link_with_txt(text_before='KlocWork server ', link_text='URL', link=kw_server, text_after='')
    html_builder.add_empty_space()

    for project_problems in build_problems_from_kw_server:
        # The following variable will be used in case of a Manual triggered build to show the report without the tables and charts (for zero issues)
        found_zero_problems = False
        # If no errors found, can proceed, unless it's a manually triggered build...
        if len(project_problems.PROBLEMS) == 0:
            found_zero_problems = True
            if not force_display_queries:
                continue

        html_builder.add_strong_with_soft_line(
            strong_txt='New and Existing problems detected for {} project:'.format(project_problems.PROJECT), soft_txt=len(project_problems.PROBLEMS))

        # Building and adding KW query URL
        url = '{kw_server}/review/insight-review.html#issuelist_goto:project={project},' \
              'searchquery=build%253A\'{build_name}\'+grouping%253Aoff+{query},sortcolumn=id,sortdirection=ASC,start=0,view_id=1'. \
            format(kw_server=kw_server,
                   project=project_problems.PROJECT_LINK,
                   build_name=project_problems.BUILD_NAME,
                   query=project_problems.QUERY.replace('+', '%252B').replace(':', '%253A').replace(',','%252C').replace(' ', '+'))
        print('"{}"'.format(url))
        html_builder.add_link_with_txt(text_before='KW Build URL: ',
                                       link_text='{}-{}'.format(project_problems.PROJECT,
                                                                project_problems.BUILD_NAME),
                                       link=url,
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
                plotter = Plotter()
                pie_chart_file_path = join(dirname(html_output_file), '{}.png'.format(project_problems.BUILD_NAME))
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
            for num, problem in enumerate(sorted(project_problems.PROBLEMS, key=lambda k: k.SEVERITY_CODE), 1):
                even = "even" if (num % 2) else "odd"
                html_builder.add_plain_html("<td class=\"{}\"><div>#{}: <span class=\"link-text\"><a href={}>{}</a></span></div><div class=\"kw-issue-list-small kw-issue-list-gray\"> \
                        <span>{}</span> | {} | {}</div><div class=\"kw-issue-list-small kw-issue-list-gray\">Code: {} | Severity: {} | State: {} | Status: {} | \
                        Message: {}</div></td></tr>".format(even,
                                                            problem.ID,
                                                            problem.URL,
                                                            problem.TITLE,
                                                            problem.FILE,
                                                            problem.FUNCTION,
                                                            problem.LINE,
                                                            problem.CODE,
                                                            problem.SEVERITY,
                                                            problem.STATE,
                                                            problem.STATUS,
                                                            problem.MESSAGE))
            html_builder.add_plain_html("</table></body></html>")

        html_builder.add_empty_space()

    return html_builder.finish_html(), attached_diagrams_list


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


def get_klocwork_issues_for_build(build_name, username, login_token, kw_project, kw_server, query_param=''):
    """ Function to retrieve issues for build from KW """
    data = {
        'user': username,
        'ltoken': login_token,
        'project': kw_project,
        'action': 'search',
        'query': 'build:{} grouping:off {}'.format(build_name, query_param)
    }
    url = "{}/review/api".format(kw_server)
    res = requests.post(url, data=data, verify=False)
    issues = res.text
    # print (issues)
    return [issue for issue in issues.split('\n') if issue]


def check_kw_project_builds_exist(build_names, username, login_token, kw_projects, kw_server):
    all_found = True

    for build_name, proj_name in zip(build_names, kw_projects):
        print('Checking build {} existance in project {}...'.format(build_name, proj_name))
        kw_builds = get_klocwork_builds(username=username,
                                        login_token=login_token,
                                        kw_project=proj_name,
                                        kw_server=kw_server)

        for build in kw_builds:
            if build['name'] == build_name:
                break
        else:
            print('Could not find build: {} in project: {} on KW server: {}!!!'.format(build_name, proj_name, kw_server))
            all_found = False

    return all_found

def get_klocwork_problems_from_web_api(build_names, username, login_token, kw_projects, project_names_to_link, kw_server, query_params):
    build_problems_from_kw_server = []
    for build_name, proj_name, proj_name_link in zip(build_names, kw_projects, project_names_to_link):
        for query in query_params:
            kw_issues = get_klocwork_issues_for_build(build_name=build_name,
                                            username=username,
                                            login_token=login_token,
                                            kw_project=proj_name,
                                            kw_server=kw_server,
                                            query_param=query)
            problems_list = []

            if kw_issues:
                print('\nFound issues for project: {} project_link: {} build: {} ::'.
                      format(proj_name, proj_name_link, build_name))
            for i, element in enumerate(kw_issues, 1):
                # print(i)
                if not element:
                    continue
                issue = loads(element)
                print('-->Found issue: {} status: {} severity: {} state: {}\nfile: {} method: {} line: {} message: {}\nurl: {}'.
                      format(issue['title'],
                             issue['status'],
                             issue['severity'],
                             issue['state'],
                             issue['file'].split('\\')[-1],
                             issue['method'],
                             issue['line'],
                             issue['message'],
                             issue['url']))
                problems_list.append(WEB_PROBLEM(ID=issue['id'],
                                                 URL=issue['url'],
                                                 TITLE=issue['title'],
                                                 FILE=issue['file'],
                                                 LINE=issue['line'],
                                                 FUNCTION=issue['method'],
                                                 CODE=issue['code'],
                                                 MESSAGE=issue['message'],
                                                 SEVERITY=issue['severity'],
                                                 SEVERITY_CODE=issue['severityCode'],
                                                 STATE=issue['state'],
                                                 STATUS=issue['status']))

            build_problems_from_kw_server.append(BUILD_PROBLEMS(PROJECT=proj_name,
                                                                PROJECT_LINK=proj_name_link,
                                                                BUILD_NAME=build_name,
                                                                QUERY=query,
                                                                PROBLEMS=problems_list))

    return build_problems_from_kw_server


def main(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("-b", "--build_names", help="KW Build names (order should match the project names)", required=True, nargs='+', type=str)
    parser.add_argument("-prbr", "--pr_branch_name", help="Pull request branch name", default='')
    parser.add_argument("-br", "--build_branch_name", help="Build branch name", default='')
    parser.add_argument("-bu", "--build_url", help="KW Build pipeline URL", required=True, default='')
    parser.add_argument("-pr", "--pr_url", help="Pull Request URL", required=True, default='')
    parser.add_argument("-html", "--html_output_file", help="HTML output file path", required=True)
    parser.add_argument('-proj', "--project_names", help="KW Project names (order should match the report xmls)",
                        nargs='+', type=str, required=True)
    parser.add_argument('-pl', "--project_names_to_link", help="KW Project names to link - "
                                                               "if name of the project not matching the query"
                                                               "(order should match the report xmls)",
                        nargs='+', type=str, required=True)
    parser.add_argument("-s", "--kw_server", help="Klocwork server url", required=True)
    parser.add_argument("-t", "--login_token", help="Token to access KW", default=None)
    parser.add_argument("-u", "--username", help="Username to access KW", default=None)
    parser.add_argument('-p', '--password', help="Password for smtpauth mail")
    parser.add_argument('-at', "--attached_files", help="KW detailed report files to be attached to the report mail",
                        nargs='+', type=str)
    parser.add_argument("-m", "--email_addresses", help="Recipients email addresses, space seperated "
                                                        "optional for sending html over mail)", nargs='+', type=str)
    parser.add_argument('-all', '--get_all_existing_issues', help='Get all existing issues', action='store_true')
    parser.add_argument('-reason', '--build_reason', help="The reason of the build", default='CI')
    parser.add_argument('-us', '--build_user', help="The user name for which the build was triggered for", default='')
    parser.add_argument('-sa', "--use_smtpauth", help="Use SMTPAUTH for sending email messages with authentication "
                                                      "(requires usename and password)",
                        action="store_true")
    argv = parser.parse_args(args)

    print('Build reason: {}'.format(argv.build_reason))
    if argv.build_reason == MANUAL_BUILD_REASON:
        force_display_queries = True
    else:
        force_display_queries = False

    # Find which branch is active - if it was triggered from Pull request or manual/scheduled
    if 'System.PullRequest.SourceBranch' not in argv.pr_branch_name:
        branch_name = argv.pr_branch_name
    elif 'Build.SourceBranch' not in argv.build_branch_name:
        branch_name = argv.build_branch_name
    else:
        branch_name = 'Unknown'

    # Check that there is matching number of projects and build names
    assert len(argv.project_names) == len(argv.build_names), \
        'Project names should be the same length as the build names and the same order.'
    assert len(argv.project_names) == len(argv.project_names_to_link), \
        'Project names should be the same length as the project_names_to_link names and the same order.'
    assert argv.login_token, 'For getting information from the server, please provide login token (-t/--login_token)'
    assert argv.username, 'For getting information from the server, please provide username (-u/--username)'

    # Currently not supported
    # if argv.get_all_existing_issues:
    query_params = [MEV_QUERY_PARAM_ISSUES]

    if not check_kw_project_builds_exist(build_names=argv.build_names,
                                         username=argv.username,
                                         login_token=argv.login_token,
                                         kw_projects=argv.project_names,
                                         kw_server=argv.kw_server):
        exit(1)

    build_problems_from_kw_server = get_klocwork_problems_from_web_api(build_names=argv.build_names,
                                                                       username=argv.username,
                                                                       login_token=argv.login_token,
                                                                       kw_projects=argv.project_names,
                                                                       project_names_to_link=argv.project_names_to_link,
                                                                       kw_server=argv.kw_server,
                                                                       query_params=query_params)

    # Count number of detected errors
    number_of_problems = sum([len(proj.PROBLEMS) for proj in build_problems_from_kw_server])
    # If no errors found, finish here and don't sent report
    if number_of_problems == 0 and not force_display_queries:
        print('Found 0 problems, not creating KW html report...')
        exit(0)

    for proj in build_problems_from_kw_server:
        print('Found {} problems for project: {} project_link: {}'.
              format(len(proj.PROBLEMS), proj.PROJECT, proj.PROJECT_LINK))

    # Create HTML report when number of errors > 0
    html, attached_diagrams_list = create_html_report(build_problems_from_kw_server, argv.html_output_file,
                              argv.build_names, branch_name, argv.build_url, argv.pr_url, kw_server=argv.kw_server,
                            build_user=argv.build_user, force_display_queries=force_display_queries)

    # If Email addresses set and not empty, send the HTML report over mail
    if (argv.email_addresses):
        mailer = Mailer(from_add=FW_CI_EMAIL, to_add=argv.email_addresses, use_smtpauth=argv.use_smtpauth,
                                   smtpauth_username=argv.username, smtpauth_password=argv.password)
        senderrs = mailer.send_mail(from_mail = mailer.from_address,
                                    to_mail_list = mailer.to_addresses,
                                    subject='KW Report({}) - {}'.format(argv.build_reason, '/'.join(argv.build_names)),
                                    html_content = html,
                                    attached_files_list = argv.attached_files,
                                    embedded_image_list=attached_diagrams_list)
        if senderrs:
            print ('Errors during mail send: {}'.format(senderrs))

    # Exit with the found number of problems
    exit(number_of_problems)


if __name__ == '__main__':
    main(sys.argv[1:])
