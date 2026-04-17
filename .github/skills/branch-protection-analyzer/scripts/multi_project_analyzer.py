#!/usr/bin/env python3
"""
Multi-Project Branch Protection Analyzer

This script:
1. Parses projects.xml to get project configurations
2. Downloads manifest files from GitHub for each project
3. Applies include/exclude filters for each project
4. Checks branch protection status for eth-fw-ci-cb
5. Creates separate reports for each project
"""

import requests
import xml.etree.ElementTree as ET
import yaml
import re
import os
from datetime import datetime
from pathlib import Path
import base64
import json

# GitHub configuration
GITHUB_BASE_URL = "https://github.com/intel-innersource"
GITHUB_API_URL = "https://api.github.com/repos/intel-innersource"
PROXIES = {
    'http': 'http://proxy-dmz.intel.com:912',
    'https': 'http://proxy-dmz.intel.com:912'
}

# GitHub token configuration (optional)
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')  # Set via environment variable
HEADERS = {}
if GITHUB_TOKEN:
    HEADERS['Authorization'] = f'token {GITHUB_TOKEN}'
    print("Using GitHub token for authentication")
else:
    print("Warning: No GitHub token found. Rate limits may apply (60 requests/hour)")

def load_projects_config(config_file):
    """Load and parse the projects.xml configuration file."""
    print(f"Loading projects configuration from {config_file}...")
    
    with open(config_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Parse as YAML since the format looks like YAML
    try:
        config = yaml.safe_load(content)
        projects = config.get('projects', [])
        print(f"Found {len(projects)} projects in configuration")
        return projects
    except Exception as e:
        print(f"Error parsing configuration: {e}")
        return []

def download_manifest_file(repo_url, branch_name):
    """Download manifest file from GitHub repository."""
    print(f"Downloading manifest from {repo_url} (branch: {branch_name})")
    
    # Extract repo name from URL
    repo_name = repo_url.replace("https://github.com/intel-innersource/", "")
    
    # GitHub API URL for getting file content (always default.xml)
    api_url = f"{GITHUB_API_URL}/{repo_name}/contents/default.xml"
    params = {'ref': branch_name}
    
    try:
        response = requests.get(api_url, params=params, headers=HEADERS, proxies=PROXIES, timeout=30)
        
        if response.status_code == 200:
            file_data = response.json()
            # Decode base64 content
            content = base64.b64decode(file_data['content']).decode('utf-8')
            print(f"Successfully downloaded default.xml ({len(content)} characters)")
            return content
        else:
            print(f"Failed to download manifest: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Error downloading manifest: {e}")
        return None

def parse_manifest_xml(xml_content):
    """Parse manifest XML and extract repository information."""
    try:
        root = ET.fromstring(xml_content)
        repositories = []
        
        for project in root.findall('project'):
            name = project.get('name')
            revision = project.get('revision', 'master')
            
            if name and revision:
                repositories.append({
                    'name': name,
                    'branch': revision
                })
        
        print(f"Extracted {len(repositories)} repositories from manifest")
        return repositories
    except Exception as e:
        print(f"Error parsing manifest XML: {e}")
        return []

def apply_filters(repositories, repo_list):
    """Apply include/exclude filters to repository list."""
    if not repo_list:
        return repositories
    
    print("Applying include/exclude filters...")
    
    # Get include and exclude lists
    includes = repo_list.get('include', [])
    excludes = repo_list.get('exclude', [])
    
    # Start with all repositories if no includes specified
    filtered_repos = repositories.copy() if not includes else []
    
    # Apply includes
    if includes:
        for include_rule in includes:
            repo_pattern = include_rule.get('repo', '')
            is_regex = include_rule.get('regex', False)
            
            for repo in repositories:
                if is_regex:
                    if re.search(repo_pattern, repo['name']):
                        if repo not in filtered_repos:
                            filtered_repos.append(repo)
                else:
                    if repo_pattern == repo['name']:
                        if repo not in filtered_repos:
                            filtered_repos.append(repo)
    
    # Apply excludes
    if excludes:
        repos_to_remove = []
        for exclude_rule in excludes:
            repo_pattern = exclude_rule.get('repo', '')
            is_regex = exclude_rule.get('regex', False)
            
            for repo in filtered_repos:
                if is_regex:
                    if re.search(repo_pattern, repo['name']):
                        repos_to_remove.append(repo)
                else:
                    if repo_pattern == repo['name']:
                        repos_to_remove.append(repo)
        
        # Remove excluded repositories
        for repo in repos_to_remove:
            if repo in filtered_repos:
                filtered_repos.remove(repo)
    
    print(f"After filtering: {len(filtered_repos)} repositories (from {len(repositories)} total)")
    return filtered_repos

def check_branch_protection(repo_name, branch_name):
    """Check if branch is protected with eth-fw-ci-cb context."""
    api_url = f"{GITHUB_API_URL}/{repo_name}/branches/{branch_name}/protection"
    
    try:
        response = requests.get(api_url, headers=HEADERS, proxies=PROXIES, timeout=30)
        
        if response.status_code == 200:
            protection_data = response.json()
            
            # Check for required status checks
            required_status_checks = protection_data.get('required_status_checks')
            if not required_status_checks:
                return "protected_no_checks"
            
            contexts = required_status_checks.get('contexts', [])
            if 'eth-fw-ci-cb' in contexts:
                return "gated"
            else:
                return "protected_no_eth_fw_ci_cb"
        
        elif response.status_code == 404:
            return "no_protection"
        else:
            return "error"
    
    except Exception as e:
        print(f"Error checking protection for {repo_name}/{branch_name}: {e}")
        return "error"

def analyze_project_repositories(repositories, project_title):
    """Analyze branch protection for a list of repositories."""
    print(f"\nAnalyzing {len(repositories)} repositories for: {project_title}")
    
    results = {
        'gated': [],
        'not_gated': [],
        'skipped': [],
        'errors': []
    }
    
    for i, repo in enumerate(repositories, 1):
        repo_name = repo['name']
        branch_name = repo['branch']
        
        print(f"[{i}/{len(repositories)}] Checking {repo_name} ({branch_name})")
        
        # Skip commit SHAs and tags (40 character hex strings or tag patterns)
        if (len(branch_name) == 40 and all(c in '0123456789abcdef' for c in branch_name.lower())) or \
           branch_name.startswith('v') or \
           '.' in branch_name and branch_name.replace('.', '').replace('-', '').isdigit():
            results['skipped'].append({'repo': repo_name, 'branch': branch_name, 'reason': 'commit_sha_or_tag'})
            continue
        
        # Check branch protection
        protection_status = check_branch_protection(repo_name, branch_name)
        
        if protection_status == "gated":
            results['gated'].append({'repo': repo_name, 'branch': branch_name})
        elif protection_status == "no_protection":
            results['not_gated'].append({'repo': repo_name, 'branch': branch_name, 'reason': 'No protection'})
        elif protection_status == "protected_no_checks":
            results['not_gated'].append({'repo': repo_name, 'branch': branch_name, 'reason': 'Protected (no status checks)'})
        elif protection_status == "protected_no_eth_fw_ci_cb":
            results['not_gated'].append({'repo': repo_name, 'branch': branch_name, 'reason': 'Protected (no eth-fw-ci-cb)'})
        else:
            results['errors'].append({'repo': repo_name, 'branch': branch_name, 'reason': 'Access error'})
        
        # Add small delay to avoid rate limiting
        if i % 10 == 0:
            import time
            time.sleep(1)
    
    return results

def generate_project_report(project_config, results, output_dir):
    """Generate a detailed report for a single project."""
    project_title = project_config.get('title', 'Unknown Project')
    manifest_branch = project_config.get('manifest_branch', 'unknown')
    
    # Create safe filename
    safe_title = re.sub(r'[^\w\s-]', '', project_title).strip()
    safe_title = re.sub(r'[\s]+', '_', safe_title)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"branch_protection_report_{safe_title}_{timestamp}.txt"
    filepath = Path(output_dir) / filename
    
    total_checkable = len(results['gated']) + len(results['not_gated'])
    protection_coverage = (len(results['gated']) / total_checkable * 100) if total_checkable > 0 else 0
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"BRANCH PROTECTION ANALYSIS REPORT\n")
        f.write(f"================================================================================\n")
        f.write(f"Project: {project_title}\n")
        f.write(f"Manifest Branch: {manifest_branch}\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total repositories analyzed: {sum(len(v) for v in results.values())}\n\n")
        
        f.write(f"SUMMARY STATISTICS:\n")
        f.write(f"- Gated repositories (eth-fw-ci-cb): {len(results['gated'])}\n")
        f.write(f"- Not gated repositories: {len(results['not_gated'])}\n")
        f.write(f"- Skipped (commit SHAs/tags): {len(results['skipped'])}\n")
        f.write(f"- Errors (access issues): {len(results['errors'])}\n")
        f.write(f"- Protection coverage: {protection_coverage:.1f}% of checkable repositories\n\n")
        
        # Gated repositories
        if results['gated']:
            f.write(f"GATED REPOSITORIES (eth-fw-ci-cb protected):\n")
            f.write(f"------------------------------------------------------------\n")
            for repo in results['gated']:
                f.write(f"[GATED] {repo['repo']} ({repo['branch']})\n")
            f.write(f"\nTotal: {len(results['gated'])} repositories\n\n")
        
        # Not gated repositories
        if results['not_gated']:
            f.write(f"NOT GATED REPOSITORIES:\n")
            f.write(f"------------------------------------------------------------\n")
            for repo in results['not_gated']:
                f.write(f"[NOT GATED] {repo['repo']} ({repo['branch']}) - {repo['reason']}\n")
            f.write(f"\nTotal: {len(results['not_gated'])} repositories\n\n")
        
        # Skipped repositories
        if results['skipped']:
            f.write(f"SKIPPED REPOSITORIES (commit SHAs/tags):\n")
            f.write(f"------------------------------------------------------------\n")
            for repo in results['skipped']:
                f.write(f"[SKIPPED] {repo['repo']} ({repo['branch']})\n")
            f.write(f"\nTotal: {len(results['skipped'])} repositories\n\n")
        
        # Error repositories
        if results['errors']:
            f.write(f"ERROR REPOSITORIES (access issues):\n")
            f.write(f"------------------------------------------------------------\n")
            for repo in results['errors']:
                f.write(f"[ERROR] {repo['repo']} ({repo['branch']}) - {repo['reason']}\n")
            f.write(f"\nTotal: {len(results['errors'])} repositories\n\n")
    
    print(f"Report saved to: {filepath}")
    return filepath

def generate_summary_report(all_results, output_dir):
    """Generate a summary report for all projects."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"multi_project_summary_{timestamp}.txt"
    filepath = Path(output_dir) / filename
    
    total_projects = len(all_results)
    total_repos = sum(r['total_analyzed'] for r in all_results)
    total_gated = sum(r['gated'] for r in all_results)
    total_not_gated = sum(r['not_gated'] for r in all_results)
    total_skipped = sum(r['skipped'] for r in all_results)
    total_errors = sum(r['errors'] for r in all_results)
    
    overall_coverage = (total_gated / (total_gated + total_not_gated) * 100) if (total_gated + total_not_gated) > 0 else 0
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"MULTI-PROJECT BRANCH PROTECTION SUMMARY REPORT\n")
        f.write(f"================================================================================\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total projects analyzed: {total_projects}\n")
        f.write(f"Total repositories analyzed: {total_repos}\n\n")
        
        f.write(f"OVERALL STATISTICS:\n")
        f.write(f"- Total gated repositories (eth-fw-ci-cb): {total_gated}\n")
        f.write(f"- Total not gated repositories: {total_not_gated}\n")
        f.write(f"- Total skipped (commit SHAs/tags): {total_skipped}\n")
        f.write(f"- Total errors (access issues): {total_errors}\n")
        f.write(f"- Overall protection coverage: {overall_coverage:.1f}% of checkable repositories\n\n")
        
        f.write(f"PROJECT BREAKDOWN:\n")
        f.write(f"================================================================================\n")
        
        for result in all_results:
            checkable = result['gated'] + result['not_gated']
            coverage = (result['gated'] / checkable * 100) if checkable > 0 else 0
            
            f.write(f"\nProject: {result['name']}\n")
            f.write(f"Manifest Branch: {result['manifest_branch']}\n")
            f.write(f"Total Analyzed: {result['total_analyzed']} repositories\n")
            f.write(f"  - Gated: {result['gated']}\n")
            f.write(f"  - Not Gated: {result['not_gated']}\n")
            f.write(f"  - Skipped: {result['skipped']}\n")
            f.write(f"  - Errors: {result['errors']}\n")
            f.write(f"  - Protection Coverage: {coverage:.1f}%\n")
            f.write(f"  - Detailed Report: {result['report_file']}\n")
            f.write(f"-" * 80 + "\n")
    
    print(f"\nSummary report saved to: {filepath}")
    return filepath

def main():
    """Main function to process all projects."""
    config_file = "projects.xml"
    output_dir = Path.cwd()
    
    # Load project configurations
    projects = load_projects_config(config_file)
    
    if not projects:
        print("No projects found in configuration file")
        return
    
    print(f"\nProcessing {len(projects)} projects...\n")
    
    # Track all project results for summary
    all_results = []
    
    for i, project in enumerate(projects, 1):
        print(f"{'='*80}")
        print(f"Processing Project {i}/{len(projects)}: {project.get('title', 'Unknown')}")
        print(f"{'='*80}")
        
        # Download manifest file
        manifest_content = download_manifest_file(
            project['repo'], 
            project['manifest_branch']
        )
        
        if not manifest_content:
            print(f"Skipping project due to manifest download failure")
            continue
        
        # Parse manifest
        repositories = parse_manifest_xml(manifest_content)
        
        if not repositories:
            print(f"No repositories found in manifest")
            continue
        
        # Apply filters
        filtered_repos = apply_filters(repositories, project.get('repo_list'))
        
        if not filtered_repos:
            print(f"No repositories remaining after filtering")
            continue
        
        # Analyze branch protection
        results = analyze_project_repositories(filtered_repos, project.get('title'))
        
        # Generate report
        report_file = generate_project_report(project, results, output_dir)
        
        # Store results for summary
        project_summary = {
            'name': project.get('title', 'Unknown'),
            'manifest_branch': project.get('manifest_branch', 'unknown'),
            'total_analyzed': sum(len(v) for v in results.values()),
            'gated': len(results['gated']),
            'not_gated': len(results['not_gated']),
            'skipped': len(results['skipped']),
            'errors': len(results['errors']),
            'report_file': report_file.name
        }
        all_results.append(project_summary)
        
        print(f"\nProject {i} completed:")
        print(f"- Gated: {len(results['gated'])}")
        print(f"- Not gated: {len(results['not_gated'])}")
        print(f"- Skipped: {len(results['skipped'])}")
        print(f"- Errors: {len(results['errors'])}")
        print(f"- Report: {report_file.name}")
        print()
    
    # Generate summary report
    generate_summary_report(all_results, output_dir)
    
    print("All projects processed successfully!")

if __name__ == "__main__":
    main()
