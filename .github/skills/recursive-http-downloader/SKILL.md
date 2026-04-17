---
name: recursive-http-downloader
description: "Recursively download files from HTTP directory listings using BeautifulSoup HTML parsing. Supports session-based authentication, JSON configuration, and automatic subdirectory traversal. Use when: mirroring HTTP-served file trees, downloading build artifacts from web servers, or scraping file directories with authentication."
argument-hint: "Username, password, and path to JSON config with base_url and destination_folder"
---

# Recursive HTTP Downloader

Recursively downloads all files from an HTTP directory listing, traversing subdirectories automatically using HTML link parsing.

## Source

Based on: `tools/scripts/has_downloader/has_downloader.py`

## When to Use

- Mirroring entire directory trees served over HTTP
- Downloading build artifacts from web servers with directory listings
- Scraping authenticated file servers
- Batch-downloading files from HAS (HTTP Archive Server) or similar services

## Prerequisites

- Python 3.x
- `requests` and `beautifulsoup4` packages

```bash
pip install requests beautifulsoup4
```

## Usage

```bash
python has_downloader.py <username> <password> <config.json>
```

## Configuration File

Create a JSON config file:

```json
{
    "base_url": "https://files.example.com/builds/latest/",
    "destination_folder": "/local/path/to/download"
}
```

## How It Works

1. **Session authentication** — Creates a `requests.Session` with HTTP Basic Auth credentials
2. **Stack-based traversal** — Uses a stack (not recursion) to traverse directories:
   - Fetches the HTML page at each URL
   - Parses `<a>` tags with BeautifulSoup
   - URLs ending with `/` are subdirectories → pushed to stack
   - Other URLs are files → downloaded immediately
3. **Cycle prevention** — Tracks visited URLs to avoid infinite loops
4. **Directory mirroring** — Preserves the remote directory structure locally
5. **Streaming downloads** — Uses chunked transfer (8KB chunks) for memory efficiency

## Core Algorithm

```python
def download_recursive(session, base_url, dest_folder):
    stack = [(base_url, dest_folder)]
    visited_urls = set()

    while stack:
        url, current_folder = stack.pop()
        if url in visited_urls:
            continue
        visited_urls.add(url)

        response = session.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')

        for link in soup.find_all('a'):
            href = link.get('href')
            if not href or href == '../':
                continue

            full_url = urljoin(url, href)
            if full_url.endswith('/'):
                # Subdirectory — add to stack
                next_folder = os.path.join(current_folder, os.path.basename(href))
                stack.append((full_url, next_folder))
            else:
                # File — download
                download_file(session, full_url, current_folder)
```

## Notes

- The `../` parent directory link is explicitly skipped to prevent upward traversal
- Destination directories are created automatically via `os.makedirs`
- Each file download streams to disk to handle large files
- Authentication is session-based (credentials sent with every request)
