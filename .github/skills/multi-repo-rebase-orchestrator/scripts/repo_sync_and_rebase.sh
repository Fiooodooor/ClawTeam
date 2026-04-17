#!/bin/bash

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print messages with color
print_info() {
    echo -e "${BLUE}$1${NC}"
}

print_success() {
    echo -e "${GREEN}$1${NC}"
}

print_warning() {
    echo -e "${YELLOW}$1${NC}"
}

print_error() {
    echo -e "${RED}$1${NC}"
}

# Help display
display_help() {
	echo "Usage: $0 [project]"
	echo
	echo "Arguments:"
	echo "  project            Project type (mmg, nsc, mev). Default is mmg."
	exit 0
}

# Read repos from config file
read_repos_from_file() {
	REPOS=()
	config_file="$IMC_TOOLS_ROOT/scripts/repo_rebase_tool/repos.conf"
	if [[ ! -f "$config_file" ]]; then
		print_error "Configuration file not found: $config_file"
		exit 1
	fi
	while IFS= read -r line || [[ -n "$line" ]]; do
		[[ -z "$line" || "$line" =~ ^# ]] && continue
		REPOS+=("$line")
	done < "$config_file"
}

# Pick repos from list
read_repos_from_input() {
	REPOS=()
	all_repos=($(repo list | awk '{print $1}' | grep '^sources/'))
	echo "Available repositories (enter the number to select, or type 'done' to finish):"
	select repo in "${all_repos[@]}"; do
		if [[ "$REPLY" == "done" ]]; then
			break
		elif [[ -n "$repo" ]]; then
			REPOS+=("$repo")
			print_info "Selected repositories: ${REPOS[*]}"
		else
			print_warning "Invalid selection. Please try again."
		fi
	done
}

# Sync and rebase
sync_and_rebase() {
	if [[ -z "$IMC_TOOLS_ROOT" ]]; then
		print_error "IMC_TOOLS_ROOT is not set. Exiting."
		exit 1
	fi

	declare -A original_branches

	# Check for local changes
	for repo in $(repo list | awk '{print $1}'); do
		cd "$IMC_TOOLS_ROOT/../../../$repo" || exit 1

		if git status | grep "modified:" | grep -v "new commits\|modified content" ; then
			if [ "$choice" -eq 1 ]; then
				print_warning "Local changes detected in $repo. Stashing changes..."
				git stash
				print_info "Changes stashed in $repo"
			else
				print_warning "Local changes detected in $repo. Please resolve the changes and then press Enter to continue."
				while git status | grep "modified:" | grep -v "new commits\|modified content"; do
					read -p "Press Enter to continue after resolving the changes in $repo... "
				done
			fi
		fi

		if [[ " ${REPOS[@]} " =~ " ${repo} " ]]; then
			branch_name=$(git rev-parse --abbrev-ref HEAD)
			if [[ $branch_name == dev/* ]]; then
				original_branches[$repo]=$branch_name
				print_info "Saved branch $branch_name for $repo"
			else
				print_error "$repo isn't on a dev branch"
				exit 1
			fi
		fi

		print_info "Checking out $trunk_branch in $repo"
		git checkout $trunk_branch
		cd -
	done

	# Sync repos
	print_info "Syncing repositories..."
	repo sync -j72 -d
	if [ $? -ne 0 ]; then
		print_error "repo sync failed. Exiting."
		exit 1
	fi

	# Rebase each repo
	for repo in "${REPOS[@]}"; do
		cd "$IMC_TOOLS_ROOT/../../../$repo" || exit 1
		git remote update
		branch=${original_branches[$repo]}
		print_info "Checking out ${original_branches[$repo]} in $repo"
		git checkout "$branch"

		git remote update
		git pull -r

		print_info "Rebasing $branch onto $trunk_branch in $repo"
		git rebase "$trunk_branch"
		if [ $? -ne 0 ]; then
			print_error "Conflict detected in $repo. Please resolve it."
			while [ -d ".git/rebase-merge" ] || [ -d ".git/rebase-apply" ]; do
				read -p "Press Enter after resolving the conflict... "
			done
		fi
		cd -
	done

	print_success "Sync and rebase completed."
}

# Default project
project="mmg"

# Parse args
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
	display_help
elif [[ -n "$1" ]]; then
	project="$1"
fi

# Set environment and trunk based on project
case $project in
	mmg)
		$IMC_SETENV_MMG
		trunk_branch="m/mev-trunk"
		;;
	nsc)
		$IMC_SETENV_NSC
		trunk_branch="m/nss-ip-bts-trunk"
		;;
	mev)
		$IMC_SETENV_MEV
		trunk_branch="m/mev-trunk"
		;;
	*)
		print_error "Invalid project type. Exiting."
		exit 1
		;;
esac

# Repo selection
print_info "How would you like to select repositories?"
print_info "  1 - Load from config file"
print_info "  2 - Pick from a list"
read -p "Enter your choice (1 or 2): " repo_choice

if [[ "$repo_choice" == "1" ]]; then
	read_repos_from_file
elif [[ "$repo_choice" == "2" ]]; then
	read_repos_from_input
else
	print_error "Invalid choice. Exiting."
	exit 1
fi

# Local changes handling
print_info "What should be done if local changes are found?"
print_info "  1 - Stash them automatically"
print_info "  2 - Pause so you can handle them yourself"
read -p "Enter your choice (1 or 2): " choice

if [[ "$choice" != "1" && "$choice" != "2" ]]; then
	print_error "Invalid choice. Exiting."
	exit 1
fi

sync_and_rebase
