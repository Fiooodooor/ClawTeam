#!/usr/bin/env python3
"""
List Files Tool for LangChain Agent

This tool allows the agent to list files and directories in a given path.
"""

import logging
from pathlib import Path
from langchain_core.tools import tool

@tool
def list_files(directory_path: str) -> dict:
    """List contents of a local directory.

    Returns information about files and subdirectories at the specified path,
    including names, types, and sizes. Non-recursive (immediate contents only).

    Args:
        directory_path: Full path to the directory to list.

    Returns:
        dict: Contains:
            - status: "success" or "error"
            - directory: The listed path
            - count: Number of items found
            - items: List of entries with name, type ("file"/"directory"), size
            - message: Error description (on failure)
    """
    logger = logging.getLogger('agent')
    try:
        path = Path(directory_path)
        if not path.exists():
            error_msg = f"Directory not found: {directory_path}"
            logger.error(error_msg)
            return {"status": "error", "message": error_msg}
        if not path.is_dir():
            error_msg = f"Not a directory: {directory_path}"
            logger.error(error_msg)
            return {"status": "error", "message": error_msg}
        items = []
        for p in sorted(path.iterdir()):
            if p.is_dir():
                item_type = "directory"
                size = 0
            else:
                item_type = "file"
                try:
                    size = p.stat().st_size
                except Exception:
                    size = -1
            items.append({
                "name": str(p.name),
                "type": item_type,
                "size": size
            })
        logger.debug(f"Listed {len(items)} items in {directory_path}")
        return {"status": "success", "directory": directory_path, "count": len(items), "items": items}
    except Exception as e:
        error_msg = f"Error listing files in {directory_path}: {e}"
        logger.error(error_msg)
        return {"status": "error", "message": error_msg}

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
    if len(sys.argv) < 2:
        print("Usage: python3 list_files.py <directory_path>")
        exit(1)
    result = list_files.invoke({"directory_path": sys.argv[1]})
    print("\n" + "="*80)
    print("DIRECTORY LISTING")
    print("="*80)
    if result["status"] == "success":
        print(f"Directory: {result['directory']}")
        print(f"Items: {result['count']}")
        for item in result["items"]:
            print(f"  - {item['name']}\t[{item['type']}]\t{item['size']} bytes")
    else:
        print(f"Error: {result['message']}")
    print("="*80)
