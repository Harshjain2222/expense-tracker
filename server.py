from fastmcp import FastMCP
from main import app # Import your

# Convert FastAPI app to MCP server
mcp = FastMCP.from_fastapi(
    app=app,
    name="Expense Tracker server",
)

if __name__ == "__main__":
    mcp.run()