import os, json, datetime
from dotenv import load_dotenv
import asyncpg, jwt
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers

load_dotenv()  
mcp = FastMCP("ExpenseTracker")

JWT_SECRET = os.environ["JWT_SECRET"]
DATABASE_URL = os.environ["DATABASE_URL"]   # pooled Neon URL, WITHOUT &channel_binding=require
CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), "categories.json")

_pool = None
async def pool():
    global _pool
    if _pool is None:
        # statement_cache_size=0 is required with Neon's pooler (pgbouncer)
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5,
                                          statement_cache_size=0)
    return _pool

def current_user_id() -> int:
    auth = get_http_headers(include_all=True).get("authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    try:
        return int(jwt.decode(token, JWT_SECRET, algorithms=["HS256"])["sub"])
    except Exception:
        raise ValueError("Unauthorized: missing or invalid/expired token. Please log in again.")

def _row(r):
    d = dict(r)
    d["amount"] = float(d["amount"])
    d["date"] = d["date"].isoformat()
    return d

def _d(s): return datetime.date.fromisoformat(s)

@mcp.tool()
async def add_expense(amount: float, category: str, date: str, note: str = ""):
    """Add an expense for the current user. date is YYYY-MM-DD; use today's date if not given."""
    if amount <= 0:
        return {"status": "error", "message": "amount must be positive"}
    uid = current_user_id()
    p = await pool()
    row = await p.fetchrow(
        """INSERT INTO expenses (user_id, amount, category, date, description)
           VALUES ($1, $2, $3, $4, $5) RETURNING id""",
        uid, round(amount, 2), category.strip(), _d(date), note)
    return {"status": "success", "id": row["id"]}

@mcp.tool()
async def list_expenses(start_date: str, end_date: str):
    """List the current user's expenses in an inclusive date range (YYYY-MM-DD)."""
    uid = current_user_id()
    p = await pool()
    rows = await p.fetch(
        """SELECT id, date, amount, category, description FROM expenses
           WHERE user_id=$1 AND date BETWEEN $2 AND $3
           ORDER BY date DESC, id DESC""", uid, _d(start_date), _d(end_date))
    return [_row(r) for r in rows]

@mcp.tool()
async def summarize(start_date: str, end_date: str, category: str | None = None):
    """Summarize the current user's expenses by category in a date range (YYYY-MM-DD)."""
    uid = current_user_id()
    p = await pool()
    rows = await p.fetch(
        """SELECT category, SUM(amount) AS total_amount, COUNT(*) AS count FROM expenses
           WHERE user_id=$1 AND date BETWEEN $2 AND $3 AND ($4::text IS NULL OR category=$4)
           GROUP BY category ORDER BY total_amount DESC""",
        uid, _d(start_date), _d(end_date), category)
    return [{"category": r["category"], "total_amount": float(r["total_amount"]),
             "count": r["count"]} for r in rows]

@mcp.tool()
async def update_expense(expense_id: int, amount: float | None = None,
                         category: str | None = None, date: str | None = None,
                         note: str | None = None):
    """Edit one of the current user's expenses. First call list_expenses to find the correct
    id; if several rows could match, ask the user which one. Pass only the fields to change.
    date is YYYY-MM-DD. category must be one of: Food & Dining, Transportation, Shopping,
    Entertainment, Bills & Utilities, Healthcare, Travel, Education, Business, Other."""
    if amount is not None and amount <= 0:
        return {"status": "error", "message": "amount must be positive"}
    uid = current_user_id()
    p = await pool()
    old = await p.fetchrow(
        "SELECT id, date, amount, category, description FROM expenses WHERE id=$1 AND user_id=$2",
        expense_id, uid)
    if not old:
        return {"status": "not_found"}
    new = await p.fetchrow(
        """UPDATE expenses SET
             amount      = COALESCE($3, amount),
             category    = COALESCE($4, category),
             date        = COALESCE($5, date),
             description = COALESCE($6, description)
           WHERE id=$1 AND user_id=$2
           RETURNING id, date, amount, category, description""",
        expense_id, uid,
        round(amount, 2) if amount is not None else None,
        category.strip() if category else None,
        _d(date) if date else None,
        note)
    return {"status": "success", "before": _row(old), "after": _row(new)}

@mcp.resource("expense:///categories", mime_type="application/json")
def categories():
    try:
        with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return json.dumps({"categories": ["Food & Dining", "Transportation", "Shopping",
            "Entertainment", "Bills & Utilities", "Healthcare", "Travel",
            "Education", "Business", "Other"]})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    mcp.run(transport="http", host="0.0.0.0", port=port)