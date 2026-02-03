from mcp.server.fastmcp import FastMCP

from .storage import Storage
from .tools.prompts import register_tools as register_prompt_tools
from .tools.sessions import register_tools as register_session_tools

mcp = FastMCP("sidecar")
storage = Storage()
register_prompt_tools(mcp, storage)
register_session_tools(mcp, storage)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
