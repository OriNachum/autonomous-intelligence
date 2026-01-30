"""FastMCP server for qq file operations."""

from pathlib import Path

from fastmcp import FastMCP

mcp = FastMCP("qq-files")


@mcp.tool
def read_file(path: str) -> str:
    """
    Read the contents of a file.
    
    Args:
        path: Path to the file to read (absolute or relative to cwd)
    
    Returns:
        The file contents as a string
    """
    file_path = Path(path).expanduser().resolve()
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    if not file_path.is_file():
        raise ValueError(f"Not a file: {file_path}")
    
    return file_path.read_text()


if __name__ == "__main__":
    mcp.run()
