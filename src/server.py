import sys
import os

# --- МАГИЯ ПУТЕЙ (Добавить это) ---
# Получаем путь к папке, где лежит этот скрипт, и берем папку выше (..), то есть корень проекта
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# ----------------------------------

from mcp.server.fastmcp import FastMCP
from src.tools import (
    read_file, 
    write_file, 
    edit_file_lines, 
    run_command
)

# Инициализация сервера
mcp = FastMCP("Agent-Tools")

# Регистрация инструментов
mcp.add_tool(read_file)
mcp.add_tool(write_file)
mcp.add_tool(edit_file_lines)
mcp.add_tool(run_command)

if __name__ == "__main__":
    mcp.run()