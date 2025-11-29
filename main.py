import asyncio
import os
import sys
import json
from contextlib import AsyncExitStack

import ollama
# pip install python-dotenv
from dotenv import load_dotenv 
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Загружаем переменные окружения из .env (если есть)
load_dotenv()

MODEL_NAME = "qwen3:14b"
CONFIG_FILE = "mcp_config.json"

class MCPAgent:
    def __init__(self):
        self.exit_stack = AsyncExitStack()
        self.sessions = [] 
        self.conversation_history = []

    async def connect_server(self, name, server_config):
        """Подключение к серверу на основе конфига"""
        command = server_config.get("command")
        args = server_config.get("args", [])
        env_config = server_config.get("env", {})

        # Сливаем текущее окружение с тем, что в конфиге
        # Это позволяет использовать системные PATH и API ключи
        env = os.environ.copy()
        
        # Если в конфиге есть переменные, добавляем их. 
        # Если значение начинается с $, пытаемся взять из системных переменных (безопасность)
        for k, v in env_config.items():
            if v.startswith("$"):
                env_var_name = v[1:]
                env[k] = os.getenv(env_var_name, "")
            else:
                env[k] = v

        print(f"🔌 Connecting to MCP: {name} ({command})...")
        
        try:
            params = StdioServerParameters(command=command, args=args, env=env)
            read, write = await self.exit_stack.enter_async_context(stdio_client(params))
            session = await self.exit_stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self.sessions.append(session)
            print(f"✅ Connected: {name}")
        except Exception as e:
            print(f"❌ Failed to connect to {name}: {e}")

    async def get_all_tools(self):
        """Агрегирует инструменты со всех серверов"""
        all_tools = []
        for session in self.sessions:
            try:
                # Таймаут на получение списка инструментов, чтобы не зависало
                response = await asyncio.wait_for(session.list_tools(), timeout=5.0)
                for tool in response.tools:
                    all_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.inputSchema
                        }
                    })
            except Exception as e:
                # Не ломаем работу агента, если один из серверов тупит
                print(f"⚠️ Warning: Could not fetch tools from a session: {e}")
        return all_tools

    async def execute_tool_call(self, tool_call):
        fn_name = tool_call['function']['name']
        fn_args = tool_call['function']['arguments']
        
        print(f"⚙️ Calling: {fn_name}")
        
        # Поиск инструмента среди всех сессий
        for session in self.sessions:
            try:
                tools = await session.list_tools()
                if any(t.name == fn_name for t in tools.tools):
                    res = await session.call_tool(fn_name, fn_args)
                    
                    # Обработка разного типа контента (text/image)
                    content_blocks = []
                    for content in res.content:
                        if content.type == 'text':
                            content_blocks.append(content.text)
                        elif content.type == 'image':
                            content_blocks.append("[Image Content]")
                    
                    result_text = "\n".join(content_blocks)
                    print(f"📝 Result ({fn_name}): {result_text[:100]}...")
                    
                    return {
                        "role": "tool",
                        "name": fn_name,
                        "content": result_text
                    }
            except Exception:
                continue # Ищем в следующей сессии
        
        return {
            "role": "tool",
            "name": fn_name,
            "content": f"Error: Tool {fn_name} not found on any connected server."
        }

    async def chat_loop(self):
        # Динамический промпт на основе загруженных инструментов
        tools_info = await self.get_all_tools()
        tool_names = [t['function']['name'] for t in tools_info]
        
        system_prompt = (
            "Ты — Умный AI-Агент. У тебя есть доступ к внешним инструментам.\n"
            f"Доступные инструменты: {', '.join(tool_names)}\n"
            "1. Используй 'local-tools' для работы с файлами и кодом.\n"
            "2. Используй 'brave-search' (если есть) для поиска информации в интернете.\n"
            "3. Если не знаешь ответ, поищи информацию или проверь код."
        )
        
        self.conversation_history.append({"role": "system", "content": system_prompt})
        print(f"\n🤖 Agent ready. Loaded {len(tool_names)} tools.")

        while True:
            try:
                user_input = input("\n👤 You: ")
                if user_input.lower() in ["quit", "exit"]: break
                
                self.conversation_history.append({"role": "user", "content": user_input})

                while True:
                    available_tools = await self.get_all_tools()
                    
                    # Запрос к модели
                    response = ollama.chat(
                        model=MODEL_NAME,
                        messages=self.conversation_history,
                        tools=available_tools,
                    )
                    
                    message = response['message']
                    self.conversation_history.append(message)

                    tool_calls = message.get('tool_calls')
                    
                    if tool_calls:
                        print(f"⚡ Model uses {len(tool_calls)} tools")
                        tasks = [self.execute_tool_call(tc) for tc in tool_calls]
                        tool_results = await asyncio.gather(*tasks)
                        self.conversation_history.extend(tool_results)
                    else:
                        print(f"\n🤖 Agent: {message['content']}")
                        break

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                break

    async def run(self):
        # Чтение конфига
        if not os.path.exists(CONFIG_FILE):
            print(f"❌ Config file {CONFIG_FILE} not found!")
            # Фолбек на локальный сервер, если конфига нет
            config = {
                "mcpServers": {
                    "default": {
                        "command": sys.executable, 
                        "args": ["server.py"]
                    }
                }
            }
        else:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)

        async with self.exit_stack:
            # Перебираем все серверы из JSON и подключаем их
            servers = config.get("mcpServers", {})
            
            if not servers:
                print("⚠️ No servers defined in config.")
            
            connect_tasks = []
            for name, srv_conf in servers.items():
                connect_tasks.append(self.connect_server(name, srv_conf))
            
            # Подключаемся ко всем параллельно для скорости
            await asyncio.gather(*connect_tasks)
            
            if not self.sessions:
                print("❌ No active MCP sessions. Exiting.")
                return

            await self.chat_loop()

if __name__ == "__main__":
    agent = MCPAgent()
    asyncio.run(agent.run())