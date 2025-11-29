
import os
import asyncio

WORK_DIR = os.path.abspath("./playground")
os.makedirs(WORK_DIR, exist_ok=True)

def validate_path(rel_path: str) -> str:
    abs_path = os.path.abspath(os.path.join(WORK_DIR, rel_path))
    if not abs_path.startswith(WORK_DIR):
        raise ValueError(f"Access denied: {rel_path}")
    return abs_path

async def read_file(path: str) -> str:
    """Читает файл с номерами строк."""
    try:
        full_path = validate_path(path)
        with open(full_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            return "".join([f"{i+1}| {line}" for i, line in enumerate(lines)])
    except Exception as e: return f"Error: {e}"

async def write_file(path: str, content: str) -> str:
    """Пишет файл."""
    try:
        full_path = validate_path(path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f: f.write(content)
        return f"Saved {path}"
    except Exception as e: return f"Error: {e}"

async def edit_file_lines(path: str, start_line: int, end_line: int, new_content: str) -> str:
    """Меняет строки."""
    try:
        full_path = validate_path(path)
        with open(full_path, "r", encoding="utf-8") as f: lines = f.readlines()
        
        # Логика замены
        new_lines_list = [l + '\n' if not l.endswith('\n') else l for l in new_content.splitlines()]
        if not new_lines_list and new_content: new_lines_list = [new_content + '\n']
        
        result = lines[:start_line-1] + new_lines_list + lines[end_line:]
        
        with open(full_path, "w", encoding="utf-8") as f: f.writelines(result)
        return f"Edited {path}"
    except Exception as e: return f"Error: {e}"

async def run_command(command: str) -> str:
    """Терминал."""
    forbidden = ["rm -rf", "sudo", "../"]
    if any(bad in command for bad in forbidden): return "Forbidden."
    try:
        proc = await asyncio.create_subprocess_shell(
            command, cwd=WORK_DIR,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        return (stdout.decode() + stderr.decode()).strip() or "Done."
    except Exception as e: return f"Error: {e}"