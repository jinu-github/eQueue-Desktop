"""Entry point for the packaged server .exe - calls uvicorn directly
instead of relying on the `uvicorn` command-line tool, which isn't
available inside a frozen executable."""
import uvicorn
from main import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)