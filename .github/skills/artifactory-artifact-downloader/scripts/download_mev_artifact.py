"""
This script is used to download and process artifacts from an Artifactory repository. 
It supports downloading specific builds, extracting files, and organizing them into an output folder. 
The script also handles special cases for different project configurations and performs cleanup after execution.
Modules:
    - optparse: For parsing command-line options.
    - os: For interacting with the operating system.
    - shutil: For file operations like copying and deleting.
    - re: For regular expressions.
    - requests: For making HTTP requests.
    - tarfile: For extracting tar files.
    - json: For handling JSON data.
    - subprocess: For executing shell commands.
    - sys: For system-specific parameters and functions.
    - zstandard: For handling Zstandard-compressed files.
Functions:
    - find_file_in_folder(search_folder, regex_file_name): Searches for a file in a folder matching a regex pattern.
    - get_build_number(s, str_start, str_end): Extracts a build number from a string based on start and end markers.
    - check_build(url): Retrieves a list of files and folders from a given build URL.
    - find_fedora_version(url): Finds the Fedora version from the Artifactory folder listing.
    - find_latest_build(): Finds the latest build number for a given branch and build stream.
    - find_folder_name(html_folders_list, zip_name): Finds a folder name in an HTML folder listing that matches a regex pattern.
Command-line Options:
    -ao, --artifactory_oragon_key: Artifactory Oragon API key.
    -ai, --artifactory-igk-key: Artifactory IGK API key.
    -ail, --artifactory-il-key: Artifactory Israel API key.
    -s, --stepping: Stepping information.
    -b, --build-stream: Build stream name.
    -m, --mev-build-id: MEV build ID (can be "latest").
    -r, --mev-branch: MEV branch name.
    -p, --name-prefix: Name prefix for the project.
    -o, --output-folder: Path to the output folder.
    -l, --bid-list: Comma-separated list of BID values.
    -e, --mev-ts-erot-or-irot: Specifies whether to use "erot" or "irot" for MEV TS (default: "erot").
    -k, --kernel-version: Kernel version (default: "5.15").
    -v, --host-kernel-version: Host kernel version (default: empty).
Workflow:
    1. Parse command-line arguments.
    2. Determine the project name and file prefix based on the MEV branch and name prefix.
    3. If the MEV build ID is "latest", find the latest build number.
    4. Construct the Artifactory folder URL and retrieve Fedora version if applicable.
    5. Identify the required artifact files based on naming conventions.
    6. Download and extract the artifact files.
    7. Organize the extracted files into the output folder.
    8. Handle special cases for MEV TS and Simics configurations.
    9. Copy files to a shared location if applicable.
    10. Clean up temporary files and folders.
Notes:
    - The script assumes access to an internal Artifactory server.
    - Proxy settings are used for HTTP requests.
    - The script installs the `zstandard` library if it is not already installed.
    - Error handling is included for missing files, failed downloads, and extraction issues.
Example Usage:
    python download_mev_artifact.py -a <artifactory_key> -s <stepping> -b <build_stream> -m <mev_build_id> -r <mev_branch> -p <name_prefix> -o <output_folder> -l <bid_list>
"""
import os
import shutil
import re
import requests
import tarfile
import json
import subprocess
import sys
import argparse

try:
    import zstandard as zstd
except:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "zstandard", "--proxy=http://proxy.iil.intel.com:911"])
    # subprocess.call("pip install zstandard --proxy=http://proxy.iil.intel.com:911")
    import zstandard as zstd


def find_file_in_folder(search_folder, regex_file_name):
    found_file = ""
    for file in os.listdir(search_folder):
        if re.fullmatch(regex_file_name, file):
            found_file = file
            break
    if found_file == "":
        print(f"was not able to find file that matches {regex_file_name} in {search_folder}")
        exit(-1)
    return found_file


parser = argparse.ArgumentParser(description="Download and process Artifactory artifacts")

parser.add_argument("-ao", "--artifactory_oragon_key", type=str, dest="artifactory_oragon_key",
                    help="Artifactory Oragon key")
parser.add_argument("-ai", "--artifactory-igk-key", type=str, dest="artifactory_igk_key",
                    help="Artifactory IGK key")
parser.add_argument("-ail", "--artifactory-il-key", type=str, dest="artifactory_il_key",
                    help="Artifactory Israel key")
parser.add_argument("-s", "--stepping", type=str, dest="stepping",
                    help="Stepping", default="a0")
parser.add_argument("-b", "--build-stream", type=str, dest="build_stream",
                    help="Build stream")
parser.add_argument("-m", "--mev-build-id", type=str, dest="mev_build_id",
                    help="MEV build ID")
parser.add_argument("-r", "--mev-branch", type=str, dest="mev_branch",
                    help="MEV branch")
parser.add_argument("-p", "--name-prefix", type=str, dest="name_prefix",
                    help="Name prefix")
# parser.add_argument("-f", "--mev-file-prefix", type=str, dest="mev_file_prefix",
#                     help="MEV file prefix", required=True)
parser.add_argument("-o", "--output-folder", type=str, dest="output_folder",
                    help="Output folder")
parser.add_argument("-l", "--bid-list", type=str, dest="bid_list",
                    help="BID list separated with ','")
parser.add_argument("-e", "--mev-ts-erot-or-irot", type=str, dest="mev_ts_erot_or_irot",
                    help="For MEV TS we can choose to take erot or irot", default="erot")
parser.add_argument("-k", "--kernel-version", type=str, dest="kernel_version",
                    help="Kernel version", default="6.6.4")
parser.add_argument("-v", "--host-kernel-version", type=str, dest="host_kernel_version",
                    help="Host kernel version", default="")

args = parser.parse_args()

artifactory_oragon_key = args.artifactory_oragon_key
artifactory_igk_key = args.artifactory_igk_key
artifactory_il_key = args.artifactory_il_key

artifactory_oragon_url = "https://ubit-artifactory-or.intel.com/artifactory"
artifactory_il_url = "https://ubit-artifactory-il.intel.com/ui/repos/tree/General/bkcsuccessfullci-il-local"
artifactory_igk_url = "https://af01p-igk.devtools.intel.com/artifactory"

artifactory_oragon_path = "mountevans_sw_bsp-or-local"
artifactory_igk_path = "mountevans_sw_bsp-igk-local"
artifactory_il_path = "mountevans_sw_bsp-igk-local"

artifactory_url = None
artifactory_path = None
artifactory_key = None


def get_build_number(s, str_start, str_end):
    try:
        start = s.index(str_start, 0) + len(str_start)
        end = s.index(str_end, start)
        return s[start:end]
    except Exception as e:
        print(f"could not found build number {s}, Exception: {e}")
        return False


# input is url of a candidate build for example "https://ubit-artifactory-or.intel.com/artifactory/mountevans_sw_bsp-or-local/builds/official/mev-release/ci/mev-release-ci-6840/"
# returns a list of the files and folder in
def check_build(url, artifactory_key):
    with requests.Session() as session:
        session.trust_env = False
        res = session.get(url, headers={'X-JFrog-Art-Api': artifactory_key})
        deploy_data = res.text.splitlines()
        return deploy_data


def find_fedora_version(url: str) -> str:
    with requests.Session() as session:
        session.trust_env = False
        response = session.get(url, headers={'X-JFrog-Art-Api': artifactory_key})
        data = response.text.splitlines()
        fedora_pattern = r'fedora\d+'

        for i in data:
            match = re.search(fedora_pattern, i)
            if match:
                return match.group()

    return None


def find_latest_build(artifactory_url, artifactory_key):
    try:
        new_list = []
        url = f"{artifactory_url}/builds/official/{mev_branch}/{build_stream}"
        with requests.Session() as session:
            session.trust_env = False
            response = session.get(url, headers={'X-JFrog-Art-Api': artifactory_key})
            data = response.text.splitlines()
            for i in data:
                item = get_build_number(i, "ci-", "/")
                if not item:
                    continue
                new_list.append(int(item))
            new_list = sorted(new_list, reverse=True)
            for i in new_list:
                new_url = f"{url}/{mev_branch}-{build_stream}-{str(i)}"
                candidate_build = check_build(new_url, artifactory_key)
                if [s for s in candidate_build if "build_completed" in s]:
                    return i
                else:
                    continue
            return False
    except Exception as e:
        print(f"Error in find_latest_build.except: {e}")
        return False


stepping = args.stepping
print(f"stepping: {stepping}")

build_stream = args.build_stream
print(f"build_stream: {build_stream}")

mev_build_id = args.mev_build_id
print(f"mev_build_id: {mev_build_id}")

mev_branch = args.mev_branch
print(f"mev_branch: {mev_branch}")

name_prefix = args.name_prefix
print(f"name_prefix: {name_prefix}")

if "mmg" in mev_branch:
    if name_prefix == "simics":
        project_name = "mmg"
        mev_branch = mev_branch.replace("mmg", "mev")  # artifactory is still in mev also for mmg
    if name_prefix == "hw":
        project_name = "mmg"
        mev_branch = mev_branch.replace("mmg", "mev")  # artifactory is still in mev also for mmg
        mev_file_prefix = mev_branch.split('-')[1]
elif "nss" in mev_branch:
    project_name = "nss"
else:
    project_name = mev_branch[0:mev_branch.rfind('-')]
    mev_file_prefix = mev_branch[mev_branch.rfind('-') + 1:]
    mev_file_prefix = mev_file_prefix.replace("-", ".")

output_folder = args.output_folder
print(f"output_folder: {output_folder}")

bid_list = args.bid_list
print(f"bid_list: {bid_list}")

mev_ts_erot_or_irot = args.mev_ts_erot_or_irot
print(f"mev_ts_erot_or_irot: {mev_ts_erot_or_irot}")

kernel_version = args.kernel_version
print(f"kernel_version: {kernel_version}")

host_kernel_version = args.host_kernel_version
print(f"host_kernel_version: {host_kernel_version}")

if project_name == "mev-ts":
    mev_file_prefix = mev_branch[mev_branch.rfind('-ts') + 1:]
    secondary_build_number = mev_build_id[0:mev_build_id.rfind('.')]
    mev_build_id = mev_build_id[mev_build_id.rfind('.') + 1:]

folders_to_delete = []


def get_latest_build_and_source():
    oragon_build = find_latest_build(f"{artifactory_oragon_url}/{artifactory_oragon_path}", artifactory_oragon_key)
    il_build = find_latest_build(f"{artifactory_il_url}/{artifactory_il_path}", artifactory_il_key)
    igk_build = find_latest_build(f"{artifactory_igk_url}/{artifactory_igk_path}", artifactory_igk_key)

    il_valid = il_build is not None and il_build is not False
    oragon_valid = oragon_build is not None and oragon_build is not False
    igk_valid = igk_build is not None and igk_build is not False

    # Check each artifactory and collect valid builds
    artifactory_sources = [
        (oragon_valid, oragon_build, artifactory_oragon_url, artifactory_oragon_path, artifactory_oragon_key, "oragon"),
        (igk_valid, igk_build, artifactory_igk_url, artifactory_igk_path, artifactory_igk_key, "igk"),
        (il_valid, il_build, artifactory_il_url, artifactory_il_path, artifactory_il_key, "il")
    ]

    valid_builds = []
    for is_valid, build_num, url, path, key, name in artifactory_sources:
        if is_valid:
            print(f"Found latest build at {url} - Build number is: {build_num}")
            valid_builds.append((int(build_num), url, path, key, name))
        else:
            print(f"Failed to find latest build at {url}")
    if not valid_builds:
        print("Failed to get latest build from any source.")
        exit(-1)

    # Sort by build number (descending) and use the highest one
    valid_builds.sort(key=lambda x: x[0], reverse=True)
    
    # Get the artifactory with the highest build number
    build_number, url, path, key, name = valid_builds[0]
    
    print(f"Using latest build from {name} artifactory: {url}")
    return build_number, url, path, key


if mev_build_id == "latest":
    mev_build_id, artifactory_url, artifactory_path, artifactory_key = get_latest_build_and_source()


if project_name == "mmg" and name_prefix == "hw":
    artifactory_main_folder = f"list/{artifactory_path}/builds/official/{mev_branch}/{build_stream}/{mev_branch}-{build_stream}-{mev_build_id}"
elif project_name == "nss":
    artifactory_main_folder = f"list/nss-igk-local/builds/official/{mev_branch}/{build_stream}/{mev_branch}-{build_stream}-{mev_build_id}"
else:
    artifactory_main_folder = f"{artifactory_path}/builds/official/{mev_branch}/{build_stream}/{mev_branch}-{build_stream}-{mev_build_id}"


def get_artifactory_usage():
    session = requests.Session()
    session.trust_env = False
    base_urls = [
        (artifactory_il_url, artifactory_il_path, artifactory_il_key),
        (artifactory_igk_url, artifactory_igk_path, artifactory_igk_key),
        (artifactory_oragon_url, artifactory_oragon_path, artifactory_oragon_key),
    ]

    for url, path, key in base_urls:
        full_path = artifactory_main_folder.replace("None", path)
        full_url = f"{url}/{full_path}/"
        print(f"Trying base URL: {url}")
        
        # Use HEAD request to check existence without downloading content
        response = session.head(full_url, headers={'X-JFrog-Art-Api': key}, allow_redirects=True)

        # Check for any failure condition: HTTP errors or redirects
        if (not response.ok or 
            (response.url != full_url and response.url.rstrip('/') != full_url.rstrip('/'))):
            
            if not response.ok:
                print(f"HTTP error {response.status_code} from {full_url}")
            else:
                print(f"URL {full_url} was redirected to {response.url} - path likely doesn't exist")
            continue

        print(f"Found valid base: {url}")
        return url, full_path, key

    print("Failed to find a valid Artifactory base URL (ORAGON or IGK or Israel). Exiting.")
    exit(-1)

if artifactory_url is None:
    artifactory_url, artifactory_main_folder, artifactory_key = get_artifactory_usage()

kernel = ""
if (mev_branch == "mev-trunk" and int(mev_build_id) > 25017) or (
        mev_branch == "mev-release" and int(mev_build_id) > 6882) or (
        "mmg" in mev_branch):
    kernel = f"-{kernel_version}"

if host_kernel_version == "":
    host_kernel = kernel
else:
    host_kernel = f"-{host_kernel_version}"

fedora_version = (
    find_fedora_version(f"{artifactory_url}/{artifactory_main_folder}/deploy"))


def find_folder_name(html_folders_list, zip_name):
    start_index = html_folders_list.find("href=") + len("href=")
    stop_index = html_folders_list.find(">", start_index)
    while start_index != -1:
        # print(f"start_index: {start_index} stop_index: {stop_index}")
        filename = html_folders_list[start_index + 1:stop_index - 1]
        match = re.fullmatch(zip_name, filename)
        if match:
            print(f"found {filename}")
            return filename
        next_start_index = html_folders_list.find("href=", start_index)
        if next_start_index == -1:
            break
        start_index = next_start_index + len("href=")
        stop_index = html_folders_list.find(">", start_index)
    return ""


print(f"project_name: {project_name}")
print(f"mev_branch: {mev_branch}")

# zip folders to search for with start and ands with strings
if "mev-ts" in mev_branch:
    zip_naming = [
        (fr"deploy-sdk/oem_generic", fr"intel-ipu-eval-ssd-image-{secondary_build_number}.{mev_build_id}.tar.gz"),
        (fr"deploy-sdk/internal_only", fr"hw-flash-internal.{secondary_build_number}.{mev_build_id}.tgz")

    ]
    flash_index = 1
    ssd_index = 0
elif "nss" in mev_branch:
    zip_naming = [
        (fr"deploy/nvmupdate_package", fr"nvmupdate.*\.tar.gz")
    ]
    flash_index = 0
elif name_prefix == "simics":
    zip_naming = [
        (fr"deploy", fr"{project_name}-{name_prefix}-{stepping}{kernel}-{build_stream}-{mev_file_prefix}.\d+-mev.tgz"),
        (fr"deploy", fr"ipu{kernel}-{build_stream}-{mev_file_prefix}.\d+.\d+-imc.tgz")
    ]
    ssd_index = 0
    flash_index = 1
elif (mev_branch == "mev-release" and int(mev_build_id) >= 12087) or (mev_branch == "mev-trunk" and int(mev_build_id) >= 81918):
    zip_naming = [
        (fr"deploy", fr"ipu{host_kernel}-{build_stream}-{mev_file_prefix}.\d+.\d+.\d+.\d+-{fedora_version}.tgz"),
        (fr"deploy",
         fr"{project_name}-{name_prefix}-{stepping}{kernel}-{build_stream}-{mev_file_prefix}.\d+.\d+.\d+-mev.tgz"),
        (fr"deploy",
         fr"ipu{kernel}-{build_stream}-{mev_file_prefix}.\d+.\d+.\d+.\d+_{project_name}-{name_prefix}-{stepping}-imc.tgz")
    ]
    kernel_index = 0
    ssd_index = 1
    flash_index = 2
else:
    zip_naming = [
        (fr"deploy",
         fr"{project_name}-{name_prefix}-{stepping}{kernel}-{build_stream}-{mev_file_prefix}.\d+.\d+-{fedora_version}.tgz"),
        (fr"deploy", fr"{project_name}-{name_prefix}-{stepping}{kernel}-{build_stream}-{mev_file_prefix}.\d+-mev.tgz"),
        (fr"deploy", fr"ipu{kernel}-{build_stream}-{mev_file_prefix}.\d+.\d+-imc.tgz")
    ]
    kernel_index = 0
    ssd_index = 1
    flash_index = 2
print(f"zip_naming: {zip_naming}")

zip_folders = []

for zip_folder, zip_name in zip_naming:
    with requests.Session() as session:
        session.trust_env = False
        response = session.get(f"{artifactory_url}/{artifactory_main_folder}/{zip_folder}",
                               headers={'X-JFrog-Art-Api': artifactory_key})
        if response.status_code not in [200, 201, 204]:
            print(
                f"Error: Received unexpected status code {response.status_code} for URL {artifactory_url}/{artifactory_main_folder}/{zip_folder}")
            exit(-1)
        print(f"{artifactory_url}/{artifactory_main_folder}/{zip_folder}")
        folders_html = response.content.decode('utf-8')

    zip_name = find_folder_name(folders_html, zip_name)
    if zip_name == "":
        print(
            f"Couldn't find file that fits {zip_name} in {artifactory_url}/{artifactory_main_folder}/{zip_folder}")
        exit(-1)
    zip_folders.append((zip_folder, zip_name))

print(f"zip_folders: {zip_folders}")

cwd = os.getcwd()
for zip_folder, zip_name in zip_folders:
    # download file
    zip_url = f"{artifactory_url}/{artifactory_main_folder}/{zip_folder}/{zip_name}"
    print(f"zip_url: {zip_url}")
    with requests.Session() as session:
        session.trust_env = False
        response = session.get(zip_url, headers={'X-JFrog-Art-Api': artifactory_key})
        local_path = fr"{cwd}/{zip_name}"
        print(f"local_path: {local_path}")
        open(local_path, 'wb').write(response.content)
        folders_to_delete.append(local_path)
        # unzip
        try:
            tar = tarfile.open(local_path, "r:gz")
            print(f'tar.extractall: {zip_name.replace(".tgz", "").replace(".tar.gz", "")}')
            tar.extractall(path=zip_name.replace(".tgz", "").replace(".tar.gz", ""))
            tar.close()
        except tarfile.ReadError:
            # copy zstandard
            dctx = zstd.ZstdDecompressor()
            output_path = local_path.replace(".tgz", "_copied.tgz")
            print(f"in except tarfile.ReadError: {output_path}")
            with open(local_path, 'rb') as ifh, open(output_path, 'wb') as ofh:
                dctx.copy_stream(ifh, ofh)
            print(f"in except tarfile.ReadError:local_path : {local_path}")
            new_folder = local_path.replace(".tgz", "")
            os.mkdir(new_folder)
            print(f"in except tarfile.ReadError:new_folder : {new_folder} output_path :{output_path}")
            subprocess.call(["tar xvf {} -C {}".format(output_path, new_folder)], shell=True)

        folders_to_delete.append(local_path.replace(".tgz", "").replace(".tar.gz", ""))
# download version_report.json
file_version_report_url = ""
with requests.Session() as session:
    session.trust_env = False
    response = session.get(f"{artifactory_url}/{artifactory_main_folder}", headers={'X-JFrog-Art-Api': artifactory_key})
    main_folders_html = response.content.decode('utf-8')

if "version_report.json" in main_folders_html:
    file_version_report_url = f"{artifactory_url}/{artifactory_main_folder}/version_report.json"
    print(f"file_version_report_url: {file_version_report_url}")
    with requests.Session() as session:
        session.trust_env = False
        response = session.get(file_version_report_url, headers={'X-JFrog-Art-Api': artifactory_key})
        local_path_version_report = fr"{os.getcwd()}/version_report.json"
        print(f"local_path_version_report: {local_path_version_report}")
        open(local_path_version_report, 'wb').write(response.content)

if project_name == "mev-ts":
    print(f"delete {output_folder}")
    os.rmdir(output_folder)
    print(f"create {output_folder}")
    os.mkdir(output_folder)
    bid_list_sep = bid_list.split(",")
    for bid in bid_list_sep:
        zip_folder, zip_name = zip_folders[flash_index]
        zip_name = zip_name.replace(".tgz", "").replace(".tar.gz", "")
        src_nvm_image_bin = fr"{cwd}/{zip_name}/anvm_images/image_64M/pisgah_24g_micron_ep_single_qsfp_0x1c03/{bid}/{bid}.bin"
        dst_nvm_image_bin = fr"{output_folder}/nvm-image_{bid}.bin"
        print(f"copy {src_nvm_image_bin} to {dst_nvm_image_bin}")
        shutil.copy(src_nvm_image_bin, dst_nvm_image_bin)

    # copy SSD file
    zip_folder, zip_name = zip_folders[ssd_index]
    zip_name = zip_name.replace(".tgz", "").replace(".tar.gz", "")
    src_ssd = fr"{cwd}/{zip_name}/{zip_name}/SSD/ssd-image-mev.bin"
    print(subprocess.check_output([f"cd {cwd} && ls"], shell=True).decode('utf-8'))
    print(subprocess.check_output([f"cd {cwd}/{zip_name} && ls"], shell=True).decode('utf-8'))
    print(subprocess.check_output([f"cd {cwd}/{zip_name}/{zip_name} && ls"], shell=True).decode('utf-8'))
    print(subprocess.check_output([f"cd {cwd}/{zip_name}/{zip_name}/SSD && ls"], shell=True).decode('utf-8'))
    dst_ssd = fr"{output_folder}/ssd-image-mev.bin"
    print(f"copy {src_ssd} to {dst_ssd}")
    shutil.copy(src_ssd, dst_ssd)
elif project_name == "nss":
    zip_folder, zip_name = zip_folders[flash_index]
    zip_name = zip_name.replace(".tgz", "").replace(".tar.gz", "")

    # copy bl1
    bl1_path = fr"{cwd}/{zip_name}/nvmupdate_package/nsc-simics-a0-imc/bl1-simics.bin"
    # Check if bl1_path exists
    if not os.path.exists(bl1_path):
        print(f"Error: BL1 file not found at {bl1_path}")
    else:
        print(f"found BL1 file {bl1_path}")
    dst_bl1_bin = fr"{output_folder}/bl1.simics.bin"
    print(f"copy {bl1_path} to {dst_bl1_bin}")
    shutil.copy(bl1_path, dst_bl1_bin)

    # copy hifmc-fw-*.elf
    elf_folder = fr"{cwd}/{zip_name}/nvmupdate_package/nsc-simics-a0-imc"
    elf_files = [f for f in os.listdir(elf_folder) if f.startswith(f"hifmc-fw-") and f.endswith(".bin")]
    if len(elf_files) == 0:
        print(f"No matching elf file found in {elf_folder}")
    src_elf = os.path.join(elf_folder, elf_files[0])
    dst_elf = fr"{output_folder}/{elf_files[0]}"
    print(f"copy {src_elf} to {dst_elf}")
    shutil.copy(src_elf, dst_elf)

    # copy NVM file
    nvm_path = fr"{cwd}/{zip_name}/nvmupdate_package/nsc-simics-a0-imc/nvm-image-cnic/super_images/CNIC_IROT_128/image_128M_CNIC_phase2/image_128M_CNIC_phase2_3_8_boot_for_image_128M_CNIC_phase2/image_128M_CNIC_phase2_3_8_boot_for_image_128M_CNIC_phase2.bin"
    # Check if nvm exists
    if not os.path.exists(nvm_path):
        print(f"Error: nvm file not found at {nvm_path}")
    else:
        print(f"found nvm file {nvm_path}")
    dst_nvm = fr"{output_folder}/image_128M_CNIC_phase2_3_8_boot_for_image_128M_CNIC_phase2.bin"
    print(f"copy {nvm_path} to {dst_nvm}")
    shutil.copy(nvm_path, dst_nvm)

else:
    # move files to output folder
    bid_list_sep = bid_list.split(",")
    for bid in bid_list_sep:
        zip_folder, zip_name = zip_folders[flash_index]
        zip_name = zip_name.replace(".tgz", "")
        build_id = zip_name.split('.')[0]
        if mev_file_prefix == "ts.trunk" and mev_ts_erot_or_irot.lower() == "irot":
            # src_nvm_image_bin = fr"{cwd}/mev-{name_prefix}-{stepping}{kernel}-{build_stream}-{mev_file_prefix}.{mev_build_id}-imc/imc/images/board_id/{bid}/nvm-irot-image-{build_stream}.{mev_file_prefix}.{mev_build_id}-mev-{name_prefix}-{stepping}-imc/nvm-image_{bid}.bin"
            src_nvm_image_bin = fr"{cwd}/{zip_name}/imc/images/board_id/{bid}/nvm-irot-image-{build_stream}.{mev_file_prefix}.{build_id}-mev-{name_prefix}-{stepping}-imc/nvm-image_{bid}.bin"
        else:
            # src_nvm_image_bin = fr"{cwd}/mev-{name_prefix}-{stepping}{kernel}-{build_stream}-{mev_file_prefix}.{mev_build_id}-imc/imc/images/mev-{name_prefix}-{stepping}/board_id/{bid}/nvm-image-mev-{name_prefix}-{stepping}-imc/nvm-image_{bid}.bin"
            src_nvm_image_bin = fr"{cwd}/{zip_name}/imc/images/{project_name}-{name_prefix}-{stepping}/board_id/{bid}/nvm-image-{project_name}-{name_prefix}-{stepping}-imc/nvm-image_{bid}.bin"
            src_full_switch_nvm_image_bin = fr"{cwd}/{zip_name}/imc/images/{project_name}-{name_prefix}-{stepping}/board_id/{bid}/nvm-image-{project_name}-{name_prefix}-{stepping}-imc/new-image_hw_a0_{bid}_full_switch.bin"
        dst_nvm_image_bin = fr"{output_folder}/nvm-image_{bid}.bin"
        print(f"copy {src_nvm_image_bin} to {dst_nvm_image_bin}")
        shutil.copy(src_nvm_image_bin, dst_nvm_image_bin)

        dst_full_switch_nvm_image_bin = fr"{output_folder}/new-image_hw_a0_{bid}_full_switch.bin"
        # verify the full-switch file exists 
        if os.path.isfile(src_full_switch_nvm_image_bin):
            print(f"Found full-switch file: {src_full_switch_nvm_image_bin}")
            print(f"copy {src_full_switch_nvm_image_bin} to {dst_full_switch_nvm_image_bin}")
            shutil.copy(src_full_switch_nvm_image_bin, dst_full_switch_nvm_image_bin)
        else:
            print(f"Full-switch file not found: {src_full_switch_nvm_image_bin}")
           
    # copy SSD file
    zip_folder, zip_name = zip_folders[ssd_index]
    zip_name = zip_name.replace(".tgz", "")
    if mev_file_prefix == "trunk":
        build_id = zip_name.split('-')[-2].split('.')[-1]
    else:
        build_id = '.'.join(zip_name.split('-')[-2].split('.')[-3:]) if '.' in zip_name else zip_name
    src_ssd = fr"{cwd}/{zip_name}/mev/images/nvme-image-{build_stream}.{mev_file_prefix}.{build_id}-{project_name}-{name_prefix}-{stepping}.bin"
    dst_ssd = fr"{output_folder}/nvme-image-{build_stream}.{mev_file_prefix}.{build_id}-{project_name}-{name_prefix}-{stepping}.bin"
    print(f"copy {src_ssd} to {dst_ssd}")
    shutil.copy(src_ssd, dst_ssd)

    if name_prefix != "simics":
        # copy kernel file
        src_ssd = fr"{cwd}/{zip_folders[kernel_index][1]}"
        dst_ssd = fr"{output_folder}/{zip_folders[kernel_index][1]}"
        print(f"copy {src_ssd} to {dst_ssd}")
        shutil.copy(src_ssd, dst_ssd)

    if name_prefix == "simics":
        # copy bl1 file
        zip_folder, zip_name = zip_folders[flash_index]
        zip_name = zip_name.replace(".tgz", "")
        bl1_folder = fr"{cwd}/{zip_name}/imc/images"
        bl1_files = [f for f in os.listdir(bl1_folder) if
                     f.startswith(f"bl1-{project_name}-{name_prefix}-{stepping}-imc-")]
        if len(bl1_files) == 0:
            print(f"No matching BL1 file found in {bl1_folder}")
        src_bl1_bin = os.path.join(bl1_folder, bl1_files[0])
        dst_bl1_bin = fr"{output_folder}/{bl1_files[0]}"
        print(f"copy {src_bl1_bin} to {dst_bl1_bin}")
        shutil.copy(src_bl1_bin, dst_bl1_bin)

    # copy version_report file
    if file_version_report_url != "":
        src_version_report = local_path_version_report
        dst_version_report = fr"{output_folder}/version_report.json"
        print(f"copy {src_version_report} to {dst_version_report}")
        shutil.copy(src_version_report, dst_version_report)

    # write to json
    # Data to be written
    dictionary = {
        "build_number": f"{mev_build_id}"
    }

    # Serializing json
    json_object = json.dumps(dictionary, indent=4)

    # Writing to sample.json
    with open(fr"{cwd}/build_number.json", "w") as outfile:
        outfile.write(json_object)

    shutil.copy(fr"{cwd}/build_number.json", fr"{output_folder}/build_number.json")

    # copy images to SV Share
    destination_folder = f'/sv_images/BKC_releases/MEV/{build_stream}-{mev_branch}.{mev_build_id}'
    try:
        if not os.path.exists(destination_folder):
            shutil.copytree(output_folder, destination_folder)
            print(f"Folder copied successfully from {output_folder} to {destination_folder}")
        else:
            print(f"The destination folder {destination_folder} already exists. Merging files...")
            for file in os.listdir(output_folder):
                source_file = os.path.join(output_folder, file)
                destination_file = os.path.join(destination_folder, file)
                if os.path.isfile(source_file):  # Verify it's a file
                    if not os.path.exists(destination_file):
                        shutil.copy2(source_file, destination_file)
                        print(f"Copied {source_file} to {destination_file}")
                    else:
                        print(f"File {destination_file} already exists. Skipping...")
    except Exception as e:
        print(f'Failed to copy {output_folder} to {destination_folder}. Exception msg: {str(e)}')

# delete artifact folders
for folder in folders_to_delete:
    if os.path.isdir(folder):
        shutil.rmtree(folder)
    else:
        os.remove(folder)
    print(f"Deleted {folder}")

print("Done!")
