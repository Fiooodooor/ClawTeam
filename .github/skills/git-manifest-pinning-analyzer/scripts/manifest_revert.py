import xml.etree.ElementTree as ET
import re
import csv
import os
import subprocess
from datetime import datetime
import argparse

class Repo:
	"""
	Class representing a repository with path, name, and revision attributes.
	"""
	def __init__(self, path, name, revision):
		self.path = path
		self.name = name
		self.revision = revision

	def __repr__(self):
		return f"Repo(path={self.path}, name={self.name}, revision={self.revision})"

class ManifestParser:
	"""
	Class to parse the manifest XML file and identify repositories with fixed SHAs.
	"""
	def __init__(self, manifest_file):
		self.manifest_file = manifest_file
		self.repos = []

	def parse(self):
		"""
		Parse the manifest XML file and populate the repos list.
		"""
		tree = ET.parse(self.manifest_file)
		root = tree.getroot()
		for project in root.findall('project'):
			path = project.get('path')
			name = project.get('name')
			revision = project.get('revision')
			repo = Repo(path, name, revision)
			self.repos.append(repo)

	def is_fixed_sha(self, revision):
		"""
		Check if the revision is a fixed SHA (40-character hexadecimal string).
		"""
		return bool(re.match(r'^[a-f0-9]{40}$', revision))

	def get_fixed_sha_repos(self):
		"""
		Get a list of repositories with fixed SHAs.
		"""
		fixed_sha_repos = [repo for repo in self.repos if repo.revision and self.is_fixed_sha(repo.revision)]
		return fixed_sha_repos

	def get_repo_by_name(self, name):
		"""
		Get a repository by its name.
		"""
		for repo in self.repos:
			if repo.name.endswith(name):
				return repo
		return None

	def update_revisions(self, repos_to_update):
		"""
		Update the revisions in the manifest XML file for the given repositories.
		"""
		tree = ET.parse(self.manifest_file)
		root = tree.getroot()
		for project in root.findall('project'):
			name = project.get('name')
			for repo_name, master_branch in repos_to_update:
				if name.endswith(repo_name):
					project.set('revision', master_branch)
		tree.write(self.manifest_file)

def read_csv(file_path):
	"""
	Read the CSV file and return a list of tuples containing repo_name and repo_master_branch.
	"""
	repos_to_check = []
	with open(file_path, mode='r') as file:
		csv_reader = csv.DictReader(file)
		for row in csv_reader:
			repos_to_check.append((row['repo_name'], row['repo_master_branch']))
	return repos_to_check

def execute_git_commands(repo, master_branch, suffix, base_path):
	"""
	Execute git commands to handle the repository as per the requirements.
	"""
	repo_dir = os.path.join(base_path, repo.path)
	os.chdir(repo_dir)

	print(f"Working directory: {repo_dir}")

	# Remote update
	remote_update_cmd = "git remote update"
	print(f"Executing: {remote_update_cmd}")
	# subprocess.run(remote_update_cmd, shell=True, check=True)

	# Checkout to master branch
	checkout_cmd = f"git checkout {master_branch}"
	print(f"Executing: {checkout_cmd}")
	# subprocess.run(checkout_cmd, shell=True, check=True)

	# pull latest changes
	stash_and_pull_cmd = "git stash && git pull -r"
	print(f"Executing: {stash_and_pull_cmd}")
	# subprocess.run(stash_and_pull_cmd, shell=True, check=True)

	# Create backup branch
	backup_branch_cmd = f"git checkout -b {master_branch}_bkp{suffix}"
	print(f"Executing: {backup_branch_cmd}")
	# subprocess.run(backup_branch_cmd, shell=True, check=True)

	# Push backup branch
	push_backup_cmd = f"git push github-innersource {master_branch}_bkp{suffix}"
	print(f"Executing: {push_backup_cmd}")
	# subprocess.run(push_backup_cmd, shell=True, check=True)

	# Reset to fixed SHA
	reset_cmd = f"git reset --hard {repo.revision}"
	print(f"Executing: {reset_cmd}")
	# subprocess.run(reset_cmd, shell=True, check=True)

	# Push changes
	push_cmd = f"git push -f github-innersource {master_branch}"
	print(f"Executing: {push_cmd}")
	# subprocess.run(push_cmd, shell=True, check=True)

def update_manifest_and_push(parser, repos_to_update, base_path):
	"""
	Update the manifest XML file to change fixed SHAs to master branches and push the changes.
	"""
	manifest_repo_dir = os.path.join(base_path, 'sources/manifest')
	os.chdir(manifest_repo_dir)

	# Update the manifest XML file
	parser.update_revisions(repos_to_update)

	# Commit and push the changes
	commit_cmd = "git commit -am 'Revert fixed SHAs to master branches'"
	print(f"Executing: {commit_cmd}")
	# subprocess.run(commit_cmd, shell=True, check=True)

	push_cmd = "git push -f github-innersource mev-trunk"
	print(f"Executing: {push_cmd}")
	# subprocess.run(push_cmd, shell=True, check=True)

def main():
	"""
	Main function to parse the manifest file, read the CSV file, and execute git commands.
	"""
	manifest_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../manifest/default.xml'))
	csv_file = os.path.abspath(os.path.join(os.path.dirname(__file__), 'input.csv'))

	repo_updated = False
	parser = ManifestParser(manifest_file)
	parser.parse()
	repos_to_check = read_csv(csv_file)

	# Generate unique suffix based on current date and time
	now = datetime.now()
	suffix = now.strftime("_%d%m%H%M")

	# Calculate base path by navigating up from the script directory
	script_dir = os.path.dirname(os.path.abspath(__file__))
	base_path = os.path.abspath(os.path.join(script_dir, '../../../../../'))

	for repo_name, master_branch in repos_to_check:
		repo = parser.get_repo_by_name(repo_name)
		if repo and parser.is_fixed_sha(repo.revision):
			print(f"Repo with fixed SHA: {repo}")
			execute_git_commands(repo, master_branch, suffix, base_path)
			repo_updated = True

	# Update the manifest XML file and push the changes if any repo was updated
	if repo_updated:
		update_manifest_and_push(parser, repos_to_check, base_path)

if __name__ == "__main__":
	# Set up argument parser
	arg_parser = argparse.ArgumentParser(description="Script to handle repositories with fixed SHAs, use input.csv to control which repos needs update. It is recommended to run repo sync before this script.")
	arg_parser.parse_args()

	# Run the main function
	main()
