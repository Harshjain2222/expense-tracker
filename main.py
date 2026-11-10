import random
from fastmcp import FastMCP

mcp = FastMCP("Demo server")

@mcp.tool
def roll_dice(n_dice : int = 1):
    """Roll a dice with the given number of sides.""" 
    return [random.randint(1, 6) for _ in range(n_dice)]

@mcp.tool
def add_number(a : int, b : int):
    """Add two number together"""
    return a + b

if __name__ == "__main__":
    mcp.run()
