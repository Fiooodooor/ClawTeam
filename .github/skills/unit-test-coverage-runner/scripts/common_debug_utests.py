import sys
import time
import re
import os
import os.path
import shutil

def print_usage():
    print '''Correct usage (default values in parentheses):
    {}
        [--run_dir < running directory > ( current directory )]
        [--yml_file < YML file > ( current YML file )]
        [--rm_build] [--test_name < test name > (all)]
        [--debug_only] [--debug] [--help]
    '''.format(sys.argv[0])

def parse_args():
    args_len = len(sys.argv)

    # Default values to arguments
    bool_flags = ['--rm_build', '--debug', '--debug_only', '--help']
    flags = dict()
    for flag in bool_flags:
        flags[flag] = False
    flags['--run_dir'] = os.getcwd()
    flags['--test_name'] = 'all'
    flags['--yml_file'] = ''

    arg_id = 1
    while arg_id < args_len:
        flag = sys.argv[arg_id]
        if flag not in flags or flag == '--help':
            print_usage()
            quit()
        arg_id = arg_id + 1
        if flag in bool_flags:
            flags[flag] = True
            continue
        if arg_id == args_len:
            print_usage()
            quit()
        val = sys.argv[arg_id]
        flags[flag] = val
        arg_id = arg_id + 1
    flags['--debug'] = flags['--debug'] or flags['--debug_only']
    return flags

def win_setup(is_debug):
    is_win = os.path.exists('C:\mev_toolchain')
    if not is_win:
        return False
    tools_path = "C:\mev_toolchain\cygwin64\\bin\;"
    if is_debug:
        tools_path = 'C:\MinGW\\bin\;C:\Strawberry\c\\bin\;C:\mev_toolchain\cygwin64\\bin\;'
    ruby_path = 'C:\Ruby26-x64\\bin\;'
    orig_path = os.environ['PATH']
    new_path = tools_path + ruby_path + orig_path
    os.environ['PATH'] = new_path
    return True

def get_root_dir(scr_path, is_win):
    if is_win:
        scr_path = re.sub('\\\\', '/', scr_path)
    dir_tree = re.findall('(.*)\/([^\/]+)\/scripts\/.*', scr_path)
    dirs_tuple = dir_tree[0]
    return dirs_tuple[0] + "/" + dirs_tuple[1]

def change_run_dir(run_dir):
    try:
        os.chdir(run_dir)
    except:
        print("[FATAL] Failed to change directory to running directory",
            run_dir)
        quit()

def remove_build(is_rm):
    print("[INFO] removing build directory")
    if not is_rm:
        return
    if not os.path.exists('build'):
        return
    shutil.rmtree('build')

def get_yml_file(yml_file):
    if yml_file != '':
        return yml_file
    files = os.listdir('.')
    for file in files:
        if re.search('\.yml$', file):
            yml_file = file
            break
    if yml_file == '':
        print("[FATAL] Failed to find YML file in running directory")
        quit()
    print("[INFO] Building temp debug YML file from", yml_file)
    return yml_file

def build_tmp_yml(yml_file, run_dir, root_dir):
    in_path = run_dir + "/" + yml_file
    out_name = "temp_debug_utests.yml"
    out_path = run_dir + "/" + out_name
    try:
        in_fd = open(in_path)
    except:
        print("[FATAL] Failed to open YML for reading", in_path)
        quit()
    try:
        out_fd = open(out_path, 'w')
    except:
        print("[FATAL] Failed to open YML for writing", out_path)
        quit()
    root_path = root_dir + "/"
    for line in in_fd:
        out_yml_info = re.sub(":executable:\s+\S+covc.exe",
            ":executable: gcc", line)
        out_yml_info = re.sub("\- \-i gcc\.exe", "- -g -O0 #debug symbols",
            out_yml_info)
        out_yml_info = re.sub("\S+mev_tools\/", root_path, out_yml_info)
        out_fd.write(out_yml_info)

    in_fd.close()
    out_fd.close()
    os.environ['CEEDLING_MAIN_PROJECT_FILE'] = out_path
    return out_path

def run_ceedling(root_dir, test_name):
    ws_path = root_dir + "/ceedling/ceed_ws"
    ceedling_path = "/vendor/ceedling/bin/ceedling "
    ceedling_test = "test:" + test_name
    ceedling_cmd = "ruby " + ws_path + ceedling_path
    ceedling_cmd = ceedling_cmd + ceedling_test + " logging"
    print("[INFO] running ceedling", ceedling_cmd)
    sys.stdout.flush()
    rc = os.system(ceedling_cmd)
    return rc

def debug_ut(is_dbg):
    if not is_dbg:
        return
    dbg_dir = "build/test/out"
    dbg_file = ''
    if not os.path.exists(dbg_dir):
        print("[INFO] Debug directory was not found", dbg_dir)
        return
    for file in os.listdir(dbg_dir):
        if re.search('\.out$', file):
            dbg_file = file
            break
    if dbg_file == '':
        print("Failed to find debug file in dir", dbg_dir)
        return
    gdb_cmd = "gdb " + dbg_dir + "/" + dbg_file
    print("[INFO] running debugger", gdb_cmd)
    sys.stdout.flush()
    os.system(gdb_cmd)

def main():
    flags = parse_args()

    is_win = win_setup(flags['--debug'])

    root_dir = get_root_dir(sys.argv[0], is_win)

    change_run_dir(flags['--run_dir'])

    if flags['--debug_only']:
        debug_ut(True)
        quit()

    remove_build(flags['--rm_build'])

    yml_file = get_yml_file(flags['--yml_file'])

    out_yml_file = build_tmp_yml(yml_file, flags['--run_dir'], root_dir)

    rc = run_ceedling(root_dir, flags['--test_name'])
    os.remove(out_yml_file)
    if rc != 0:
        print("[ERROR] Failed to run ceedling")

    debug_ut(flags['--debug'])

if __name__ == "__main__":
    main()
