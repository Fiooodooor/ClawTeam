#!/usr/bin/env python
# coding: utf-8

import os, sys
from os.path import isfile, dirname, abspath, join
import re
import pandas as pd
import fnmatch
import argparse
ABS_SCRIPT_PATH = dirname(abspath(__file__))
sys.path.append(dirname(ABS_SCRIPT_PATH))
from pyTools.CCT.HTMLBuilder import HTMLBuilder
from pyTools.CCT.Mailer import Mailer

LOG_DO_COMPILE = 'log.do_compile'
FW_CI_EMAIL = 'eth.fw.ci@intel.com'
flags = ['D_FORTIFY_SOURCE=2', 'relro', 'fstack-protector-strong', 'Wformat -Wformat-security''O1','O2','O3','PIE','fPIC']

def create_html_report(html_output_file, branch_name, build_url, build_user, diff_flags):
    html_builder = HTMLBuilder(out_file=html_output_file)

    attached_diagrams_list = []
    html_builder.add_centered_bold_headline('Compilation Flags Changes Report')
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

    html_builder.add_empty_space()
    html_builder.add_link_with_txt(text_before='Jenkins Build ', link_text='URL', link=build_url, text_after='')
    html_builder.add_empty_space()
    html_builder.add_strong_with_soft_line(strong_txt='Changed compile flags:')
    html_builder.add_empty_space()

    table_headers = ['File', 'Flag']
    table_list = list(s.split(',') for s in diff_flags)
    html_builder.add_table(table_headers, table_list)

    return html_builder.finish_html(), attached_diagrams_list



def find(pattern, path):
    result = []
    for root, dirs, files in os.walk(path):
        for name in files:
            if fnmatch.fnmatch(name, pattern):
                result.append(os.path.join(root, name))
    return result

def main(args):
    parser = argparse.ArgumentParser(description='The log files folder and the output file name')
    parser.add_argument('-p', '--path', action='store', type=str, help='the path to folder of Yocto build')
    parser.add_argument('-f', '--out_csv_file', action='store', type=str, help='the output csv file name to create')
    parser.add_argument('-i', '--in_csv_file', action='store', type=str, help='the input file name to compare to')
    parser.add_argument('-bn', '--branch_name', action='store', type=str, help='Branch name or topic')
    parser.add_argument('-bu', '--build_url', action='store', type=str, help='Build job URL')
    parser.add_argument('-bs', '--build_user', action='store', type=str, help='The person who sent this change')
    parser.add_argument('-c', '--compare', action='store_true', help='Do compare input and output files')
    parser.add_argument('-m', '--email_addresses', help="Recipients email addresses, space seperated "
                                                        "optional for sending html over mail)", nargs='+', type=str)
    parser.add_argument('-us', '--username', help="Username for smtpauth mail", default=None)
    parser.add_argument('-ps', '--password', help="Password for smtpauth mail")
    parser.add_argument('-sa', "--use_smtpauth", help="Use SMTPAUTH for sending email messages with authentication "
                                                      "(requires usename and password)", action="store_true")

    args = parser.parse_args()

    files = find('log.do_compile', args.path)

    res = pd.DataFrame(columns=['compilation_file', 'flag'])
    counter = 0

    for _file in files:
        with open(_file,'r') as log_file:
            for line in log_file:
                for flag in flags:
                    if flag in line:
                            c_files = re.findall(("/[^/]+\.[co]"),line)
                            for f in c_files:
                                res.loc[counter] = [f, flag]
                                counter += 1
    res.to_csv(args.out_csv_file, index=False)

    # sort file
    df = pd.read_csv(args.out_csv_file)
    sorted_df = df.sort_values(by=["compilation_file","flag"],ascending=[True,True])
    sorted_df.to_csv(args.out_csv_file,index=False)

    if args.compare:
        # Check input & output files exists
        assert isfile(args.in_csv_file), 'Could not find input file to compare to: {}'.format(args.in_csv_file)
        assert isfile(args.out_csv_file), 'Could not find output file to compare to: {}'.format(args.out_csv_file)

        with open(args.in_csv_file, 'r') as in_file:
            with open(args.out_csv_file, 'r') as out_file:
                diff = set(out_file)-set(in_file)

        diff.discard('\n')
        if not diff:
            print("Both input & output files equal")
            exit(0)

        if (args.email_addresses):
            html, _ = create_html_report(html_output_file='comp_mail.html', branch_name=args.branch_name,
                                         build_url=args.build_url, build_user=args.build_user, diff_flags=diff)
            mailer = Mailer(from_add=FW_CI_EMAIL, to_add=args.email_addresses, use_smtpauth=args.use_smtpauth,
                            smtpauth_username=args.username, smtpauth_password=args.password)
            senderrs = mailer.send_mail(from_mail=mailer.from_address,
                                        to_mail_list=mailer.to_addresses,
                                        subject='Compilation flags enforcement alert',
                                        html_content=html,
                                        attached_files_list=[args.in_csv_file, args.out_csv_file])
            if senderrs:
                print('Errors during mail send: {}'.format(senderrs))


if __name__ == "__main__":
    main(sys.argv[1:])