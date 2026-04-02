import os
import requests
import argparse
import json
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

def download_file(session, url, dest_folder):
    if not os.path.exists(dest_folder):
        os.makedirs(dest_folder)

    local_filename = os.path.join(dest_folder, os.path.basename(urlparse(url).path))
    with session.get(url, stream=True) as r:
        r.raise_for_status()
        with open(local_filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    print(f"Downloaded {url} to {local_filename}")

def download_recursive(session, base_url, dest_folder):
    stack = [(base_url, dest_folder)]
    visited_urls = set()

    while stack:
        url, current_folder = stack.pop()
        if url in visited_urls:
            continue
        visited_urls.add(url)

        response = session.get(url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        for link in soup.find_all('a'):
            href = link.get('href')
            if not href or href == '../':
                continue

            full_url = urljoin(url, href)
            if full_url.endswith('/'):
                # Add subfolders to the stack for later processing
                next_folder = os.path.join(current_folder, os.path.basename(urlparse(href).path))
                stack.append((full_url, next_folder))
            else:
                # Download file
                download_file(session, full_url, current_folder)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Download files from a URL recursively with authentication.')
    parser.add_argument('username', type=str, help='Username for authentication')
    parser.add_argument('password', type=str, help='Password for authentication')
    parser.add_argument('config', type=str, help='Path to the JSON configuration file')

    args = parser.parse_args()

    with open(args.config, 'r') as f:
        config = json.load(f)

    base_url = config['base_url']
    destination_folder = config['destination_folder']

    with requests.Session() as session:
        session.auth = (args.username, args.password)
        download_recursive(session, base_url, destination_folder)

    print("All files downloaded successfully!")
