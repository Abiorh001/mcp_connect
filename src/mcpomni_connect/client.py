import asyncio
from typing import Optional, Any
from contextlib import AsyncExitStack
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from pathlib import Path
import platform
import sys
from mcp.types import ListPromptsRequest, ListResourcesRequest, ListToolsRequest
from openai import OpenAI
from dotenv import load_dotenv
import json
from mcpomni_connect.utils import logger
from mcp.client.websocket import websocket_client


class Configuration:
    """Manages configuration and environment variables for the MCP client."""

    def __init__(self) -> None:
        """Initialize configuration with environment variables."""
        self.load_env()
        self.api_key = os.getenv("OPENAI_API_KEY")

    @staticmethod
    def load_env() -> None:
        """Load environment variables from .env file."""
        load_dotenv()

    def load_config(self, file_path: str) -> dict:
        """Load server configuration from JSON file.

        Args:
            file_path: Path to the JSON configuration file.

        Returns:
            Dict containing server configuration.

        Raises:
            FileNotFoundError: If configuration file doesn't exist.
            JSONDecodeError: If configuration file is invalid JSON.
        """
        config_path = Path(file_path)
        logger.info(f"Loading configuration from: {config_path.name}")
        if config_path.name.lower() != "servers_config.json":
            raise FileNotFoundError(f"Configuration file not found: {config_path}, it should be 'servers_config.json'")
        with open(config_path, "r", encoding='utf-8') as f:
            return json.load(f)

    @property
    def openai_api_key(self) -> str:
        """Get the OpenAI API key.

        Returns:
            The API key as a string.

        Raises:
            ValueError: If the API key is not found in environment variables.
        """
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        return self.api_key

class MCPClient:
    def __init__(self, config: dict[str, Any], debug: bool = False):
        # Initialize session and client objects
        self.config = config
        self.sessions = {}
        self._cleanup_lock = asyncio.Lock()
        self.llm_config = None
        self.openai = OpenAI(api_key=self.config.openai_api_key)
        self.available_tools = {}
        self.available_resources = {}
        self.available_prompts = {}
        self.server_names = []
        self.message_history = []
        self.debug = debug
        self.system_prompt = None
        self.exit_stack = AsyncExitStack()
        

    async def llm_configs(self):
        """Load the LLM configuration"""
        llm_config = self.config.load_config("servers_config.json")["LLM"]
        try:
            model = llm_config.get("model", "gpt-4o-mini")
            temperature = llm_config.get("temperature", 0.5)
            max_tokens = llm_config.get("max_tokens", 5000)
            top_p = llm_config.get("top_p", 0)
            self.llm_config = {
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "top_p": top_p
            }
            return self.llm_config
        except Exception as e:
            logger.error(f"Error loading LLM configuration: {e}")
            return None

    async def connect_to_servers(self):
        """Connect to an MCP server"""
        server_config = self.config.load_config("servers_config.json")
        servers = [{"name": name, "srv_config": srv_config} for name, srv_config in server_config["mcpServers"].items()]
        
        successful_connections = 0
        failed_connections = []

        logger.info(f"Attempting to connect to {len(servers)} servers")
        
        for server in servers:
            try:
                await self._connect_to_single_server(server)
                successful_connections += 1
                logger.info(f"Successfully connected to server: {server.get('name', 'Unknown')}")
            except Exception as e:
                failed_server = server.get('name', 'Unknown')
                error_msg = f"Failed to connect to server {failed_server}: {str(e)}"
                logger.error(error_msg)
                failed_connections.append((failed_server, str(e)))
                continue  # Continue with next server
        
        # Log summary of connections
        logger.info(f"MCP Servers Connection summary: {successful_connections} servers connected, {len(failed_connections)} servers failed to connect")
        if failed_connections:
            logger.info("Failed connections:")
            for server, error in failed_connections:
                logger.info(f"  - {server}: {error}")
        
        if successful_connections == 0:
            raise RuntimeError("No servers could be connected. All connection attempts failed.")
        
        return successful_connections

    def _validate_and_convert_url(self, url: str, connection_type: str) -> str:
        """Validate and convert URL based on connection type."""
        if connection_type == "sse":
            if not url.startswith(("http://", "https://")):
                raise ValueError(f"Invalid SSE URL: {url}. Must start with http:// or https://")
            return url
        elif connection_type == "websocket":
            if not url.startswith(("ws://", "wss://")):
                raise ValueError(f"Invalid WebSocket URL: {url}. Must start with ws:// or wss://")
            return url
        else:
            raise ValueError(f"Invalid connection type: {connection_type}. Must be sse or websocket")

    async def _connect_to_single_server(self, server):
        try:
            connection_type = server["srv_config"].get("type", "stdio")
            logger.info(f"connection_type: {connection_type}")
            if connection_type == "sse":
                url = self._validate_and_convert_url(server["srv_config"]["url"], "sse")
                headers = server["srv_config"].get("headers", {})
                timeout = server["srv_config"].get("timeout", 5)
                sse_read_timeout = server["srv_config"].get("sse_read_timeout", 300)
                
                if self.debug:
                    logger.info(f"SSE connection to {url} with timeout {timeout}")

                transport = await self.exit_stack.enter_async_context(
                    sse_client(url, headers=headers, timeout=timeout, sse_read_timeout=sse_read_timeout)
                )
                
            elif connection_type == "websocket":
                url = self._validate_and_convert_url(server["srv_config"]["url"], "websocket")
                logger.info(f"WebSocket connection to {url}")
                if self.debug:
                    logger.info(f"WebSocket connection to {url}")
                    
                transport = await self.exit_stack.enter_async_context(
                    websocket_client(url)
                )
                
            else:
                # stdio connection (default)
                args = server["srv_config"]["args"]
                command = server["srv_config"]["command"]
                env = {**os.environ, **server["srv_config"]["env"]} if server["srv_config"].get("env") else None
                server_params = StdioServerParameters(
                    command=command,
                    args=args,
                    env=env
                )

                transport = await self.exit_stack.enter_async_context(stdio_client(server_params))

            read_stream, write_stream = transport
            session = await self.exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
            init_result = await session.initialize()
            server_name = init_result.serverInfo.name
            capabilities = init_result.capabilities
            self.server_names.append(server_name)
            
            self.sessions[server_name] = {
                "session": session,
                "read_stream": read_stream,
                "write_stream": write_stream,
                "connected": True,
                "capabilities": capabilities,
                "type": connection_type
            }
            
            if self.debug:
                logger.info(f"Successfully connected to {server_name} via {connection_type}")
                
        except Exception as e:
            if self.debug:
                logger.error(f"Failed to connect to server: {str(e)}")
            raise
        
    async def clean_up_server(self):
        """Clean up server connections individually"""
        for server_name in list(self.server_names):
            try:
                if server_name in self.sessions and self.sessions[server_name]["connected"]:
                    session_info = self.sessions[server_name]
                    try:
                        if session_info["write_stream"] and not session_info["write_stream"]._closed:
                            await session_info["write_stream"].aclose()
                            if self.debug:
                                logger.info(f"Closed write stream for {server_name}")
                            
                        if session_info["read_stream"] and not session_info["read_stream"]._closed:
                            await session_info["read_stream"].aclose()
                            if self.debug:
                                logger.info(f"Closed read stream for {server_name}")
                            
                        if session_info["session"]:
                            close_method = getattr(session_info["session"], "close", None)
                            if close_method and callable(close_method):
                                await close_method()
                                if self.debug:
                                    logger.info(f"Closed session for {server_name}")
                        
                    except Exception as e:
                        logger.error(f"Error during stream closure for {server_name}: {e}")
                    
                    # Mark as disconnected and clear references
                    self.sessions[server_name]["connected"] = False
                    self.sessions[server_name]["session"] = None
                    self.sessions[server_name]["read_stream"] = None
                    self.sessions[server_name]["write_stream"] = None
                    
                    if self.debug:
                        logger.info(f"Cleaned up server: {server_name}")
            except Exception as e:
                logger.error(f"Error cleaning up server {server_name}: {e}")
            
    async def cleanup(self):
        """Clean up all resources"""
        try:
            logger.info("Starting client shutdown...")
            
            # First make sure all servers are properly shut down
            try:
                async with asyncio.timeout(10.0):  # 5 second timeout for server cleanup
                    await self.clean_up_server()
            except asyncio.TimeoutError:
                logger.warning("Server cleanup timed out")
            except Exception as e:
                logger.error(f"Error during server cleanup: {e}")
            
            
            try:
                await self.clean_up_server()
                await self.exit_stack.aclose()
            except Exception as e:
                logger.error(f"Error closing exit stack: {e}")
            
            # Clear any remaining data structures
            self.server_names.clear()
            self.sessions.clear()
            self.available_tools.clear()
            self.available_resources.clear()
            self.available_prompts.clear()
            
            logger.info("All resources cleared")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

    async def refresh_capabilities(self):
        """Refresh the capabilities of the server and update system prompt"""
        for server_name in self.server_names:
            if not self.sessions[server_name]["connected"]:
                raise ValueError("Not connected to a server")
            # list all tools
            try:
                tools_response = await self.sessions[server_name]["session"].list_tools()
                if tools_response:
                    available_tools = tools_response.tools
                    self.available_tools[server_name] = available_tools
            except Exception as e:
                logger.info(f"{server_name} Does not support tools")
                self.available_tools[server_name] = []
            # list all resources
            try:
                resources_response = await self.sessions[server_name]["session"].list_resources()
                if resources_response:
                    available_resources = resources_response.resources
                    self.available_resources[server_name] = available_resources
            except Exception as e:
                logger.info(f"{server_name} Does not support resources")
                self.available_resources[server_name] = []
            # list all prompts
            try:
                prompts_response = await self.sessions[server_name]["session"].list_prompts()
                if prompts_response:
                    available_prompts = prompts_response.prompts
                    self.available_prompts[server_name] = available_prompts
            except Exception as e:
                logger.info(f"{server_name} Does not support prompts")
                self.available_prompts[server_name] = []
        
        if self.debug:
            logger.info(f"Refreshed capabilities for {self.server_names}")
            # Create a clean dictionary of server names and their tool names
            tools_by_server = {
                server_name: [tool.name for tool in tools]
                for server_name, tools in self.available_tools.items()
            }
            logger.info("Available tools by server:")
            for server_name, tool_names in tools_by_server.items():
                logger.info(f"  {server_name}:")
                for tool_name in tool_names:
                    logger.info(f"    - {tool_name}")
            # Create a clean dictionary of server names and their resource names
            resources_by_server = {
                server_name: [resource.name for resource in resources]
                for server_name, resources in self.available_resources.items()
            }
            logger.info("Available resources by server:")
            for server_name, resource_names in resources_by_server.items():
                logger.info(f"  {server_name}:")
                for resource_name in resource_names:
                    logger.info(f"    - {resource_name}")
            # Create a clean dictionary of server names and their prompt names
            prompts_by_server = {
                server_name: [prompt.name for prompt in prompts]
                for server_name, prompts in self.available_prompts.items()
            }
            logger.info("Available prompts by server:")
            for server_name, prompt_names in prompts_by_server.items():
                logger.info(f"  {server_name}:")
                for prompt_name in prompt_names:
                    logger.info(f"    - {prompt_name}")
            
        # Update system prompt with new capabilities
        self.system_prompt = self.generate_system_prompt()
        # update llm config
        await self.llm_configs()
        if self.debug:
            logger.info("Updated system prompt with new capabilities")
            logger.info(f"System prompt:\n{self.system_prompt}")

    # list all resources in mcp server
    async def list_resources(self):
        """List all resources"""
        resources = []
        for server_name in self.server_names:
            if self.sessions[server_name]["connected"]:
                try:
                    resources_response = await self.sessions[server_name]["session"].list_resources()
                    resources.extend(resources_response.resources)
                except Exception as e:
                    logger.info(f"{server_name} Does not support resources")
        return resources
    
    async def find_resource_server(self, uri: str) -> tuple[str, bool]:
        """Find which server has the resource
        
        Returns:
            tuple[str, bool]: (server_name, found)
        """
        for server_name, resources in self.available_resources.items():
            resource_uris = [str(res.uri) for res in resources]
            if uri in resource_uris:
                return server_name, True
        return "", False
    
    # read a resource from mcp server
    async def read_resource(self, uri: str):
        """Read a resource"""
        if self.debug:
            logger.info(f"Reading resource: {uri}")
        # add the first message to the history
        await self.add_message_to_history("user", f"Reading resource: {uri}")
        server_name, found = await self.find_resource_server(uri)
        if not found:
            error_message = f"Resource not found: {uri}"
            logger.error(error_message)
            await self.add_message_to_history("user", error_message, {"resource_uri": uri, "error": True})
            return error_message
        logger.info(f"Resource found in {server_name}")
        try:
            resource_response = await self.sessions[server_name]["session"].read_resource(uri)
            if self.debug:
                logger.info("LLM processing resource")
            llm_response = self.openai.chat.completions.create(
                model=self.llm_config["model"],
                max_tokens=self.llm_config["max_tokens"],
                temperature=self.llm_config["temperature"],
                top_p=self.llm_config["top_p"],
                messages=[
                    {
                    "role": "system", 
                    "content": "Analyze the document content and provide a clear, concise summary that captures all essential information. Focus on key points, main concepts, and critical details that give the user a complete understanding without reading the entire document. Present your summary using bullet points for main ideas followed by a brief paragraph for context when needed. Include any technical terms, specifications, instructions, or warnings that are vital to proper understanding. Do not include phrases like 'here is your summary' or 'in summary' - deliver only the informative content directly."
                },
                {"role": "user", "content": str(resource_response)}
            ]
        )
            response_content = llm_response.choices[0].message.content or ""
            if not response_content:
                response_content = "No content found for resource"
            await self.add_message_to_history("assistant", response_content)
            return response_content
        except Exception as e:
            error_message = f"Error reading resource: {e}"
            logger.error(error_message)
            await self.add_message_to_history("user", error_message, {"resource_uri": uri, "error": True})
            return error_message
    
    async def list_tools(self):
        """List all tools"""
        tools = []
        for server_name in self.server_names:
            if self.sessions[server_name]["connected"]:
                try:
                    tools_response = await self.sessions[server_name]["session"].list_tools()
                    tools.extend(tools_response.tools)
                except Exception as e:
                    logger.info(f"{server_name} Does not support tools")
        return tools
    
    async def list_prompts(self):
        """List all prompts"""
        prompts = []
        for server_name in self.server_names:
            if self.sessions[server_name]["connected"]:
                try:
                    prompts_response = await self.sessions[server_name]["session"].list_prompts()
                    prompts.extend(prompts_response.prompts)
                except Exception as e:
                    logger.info(f"{server_name} Does not support prompts")
        return prompts
    
    async def find_prompt_server(self, name: str) -> tuple[str, bool]:
        """Find which server has the prompt
        
        Returns:
            tuple[str, bool]: (server_name, found)
        """
        for server_name, prompts in self.available_prompts.items():
            prompt_names = [prompt.name for prompt in prompts]
            if name in prompt_names:
                return server_name, True
        return "", False

    async def get_prompt(self, name: str, arguments: Optional[dict] = None):
        """Get a prompt"""
        server_name, found = await self.find_prompt_server(name)
        if self.debug:
            logger.info(f"Getting prompt: {name} from {server_name}")
        if not found:
            error_message = f"Prompt not found: {name}"
            await self.add_message_to_history("user", error_message, {"prompt_name": name, "error": True})
            logger.error(error_message)
            return error_message
        try:
            # add the first message to the history to help the llm to know when to use all available tools directly
            await self.add_message_to_history("user", f"Getting prompt: {name}")
            prompt_response = await self.sessions[server_name]["session"].get_prompt(name, arguments)
            if prompt_response and prompt_response.messages:
                message = prompt_response.messages[0]
                user_role = None
                message_content = None
                if hasattr(message, 'role'):
                    user_role = message.role if message.role else "user"
                if hasattr(message, 'content'):
                    if hasattr(message.content, 'text'):
                        message_content = message.content.text
                    else:
                        message_content = str(message.content)
                
                if self.debug:
                    logger.info(f"LLM processing {user_role} prompt: {message_content}")
                messages = []
                messages.append({
                    "role": "system",
                    "content": self.system_prompt
                })
                messages.append({
                    "role": user_role,
                    "content": message_content
                })
                llm_response = self.openai.chat.completions.create(
                    model=self.llm_config["model"],
                    max_tokens=self.llm_config["max_tokens"],
                    temperature=self.llm_config["temperature"],
                    top_p=self.llm_config["top_p"],
                    messages=messages,
                )
                response_content = llm_response.choices[0].message.content or ""
                # adding the message to history helps the llm to know when to use all available tools directly
                await self.add_message_to_history("assistant", response_content)
                return response_content
        except Exception as e:
            error_message = f"Error getting prompt: {e}"
            await self.add_message_to_history("user", error_message, {"prompt_name": name, "error": True})
            logger.error(error_message)
            return error_message
    
    # add a message to the message history
    async def add_message_to_history(self, role: str, content: str, metadata: Optional[dict] = None):
        """Add a message to the message history"""
        message = {
            "role": role,
            "content": content,
            "timestamp": asyncio.get_running_loop().time(),
            "metadata": metadata or {}
        }
        self.message_history.append(message)
        if self.debug:
            logger.info(f"Added message to history: {role} - {content[:100]}")

    async def show_history(self):
        """Show the message history"""
        for i, message in enumerate(self.message_history):
            logger.info(f"Message {i}: {message['role']} - {message['content']}")
    async def clear_history(self):
        """Clear the message history"""
        self.message_history = []
        if self.debug:
            logger.info("Message history cleared")
    async def save_message_history_to_file(self, file_path: str):
        """Save the message history to a file"""
        with open(file_path, "w") as f:
            for message in self.message_history:
                f.write(f"{message['role']}: {message['content']}\n")
        if self.debug:
            logger.info(f"Message history saved to {file_path}")
    # process a query using OpenAI and available tools
    async def process_query(self, query: str) -> str:
        """Process a query using OpenAI and available tools"""
        # Ensure system prompt is updated
        if not self.system_prompt:
            self.system_prompt = self.generate_system_prompt()
            

        # add user query to history
        await self.add_message_to_history("user", query)

        # prepare messages for OpenAI
        messages = []

        # add system prompt and user query to messages
        messages.append({
                "role": "system",
                "content": self.system_prompt
        })

        # track assistant with tool calls and pending tool responses
        assistant_with_tool_calls = None
        pending_tool_responses = []
        
        # process message history in order
        for _, message in enumerate(self.message_history):
            if message["role"] == "user":
                # First flush any pending tool responses if needed
                if assistant_with_tool_calls and pending_tool_responses:
                    messages.append(assistant_with_tool_calls)
                    messages.extend(pending_tool_responses)
                    assistant_with_tool_calls = None
                    pending_tool_responses = []

                # then add user message to messages that will be sent to OpenAI
                messages.append({
                "role": "user",
                    "content": message["content"]
                })

            elif message["role"] == "assistant":
                # check if the assistant with tool call
                metadata = message.get("metadata", {})
                if metadata.get("has_tool_calls", False):
                    # If we already have a pending assistant with tool calls, flush it
                    if assistant_with_tool_calls:
                        messages.append(assistant_with_tool_calls)
                        messages.extend(pending_tool_responses)
                        pending_tool_responses = []

                    # Store this assistant message for later (until we collect all tool responses)
                    assistant_with_tool_calls = {
                        "role": "assistant",
                        "content": message["content"],
                        "tool_calls": metadata.get("tool_calls", [])
                    }
                else:
                    # Regular assistant message without tool calls
                    # First flush any pending tool calls
                    if assistant_with_tool_calls:
                        messages.append(assistant_with_tool_calls)
                        messages.extend(pending_tool_responses)
                        assistant_with_tool_calls = None
                        pending_tool_responses = []

                    # add the regular assistant message to messages
                    messages.append({
                        "role": "assistant",
                        "content": message["content"]
                    })
            elif message["role"] == "tool" and "tool_call_id" in message.get("metadata", {}):
                # Collect tool responses
                # Only add if we have a preceding assistant message with tool calls
                if assistant_with_tool_calls:
                    pending_tool_responses.append({
                        "role": "tool",
                        "content": message["content"],
                        "tool_call_id": message["metadata"]["tool_call_id"]
                    })
            
            elif message["role"] == "system":
                # add system message to messages
                messages.append({
                    "role": "system",
                    "content": message["content"]
                })
        
        # Flush any remaining pending tool calls at the end
        if assistant_with_tool_calls:
            messages.append(assistant_with_tool_calls)
            messages.extend(pending_tool_responses)

        
        if self.debug:
            logger.info(f"Prepared {len(messages)} messages for OpenAI")
            for i, message in enumerate(messages):
                role = message['role']
                has_tool_calls = 'tool_calls' in message
                preview = message['content'][:50] + "..." if message['content'] else ""
                logger.info(f"Message {i}: {role} {'with tool_calls' if has_tool_calls else ''} - {preview}")

        # make sure we have the latest tools
        if not self.available_tools:
            await self.refresh_capabilities()

        # list available tools
        tools = await self.list_tools()
        available_tools = [{
            "type": "function",
            "function": {
            "name": tool.name,
            "description": tool.description,
                "parameters": tool.inputSchema
            }
        } for tool in tools]

        if self.debug:
            tool_names = [tool["function"]["name"] for tool in available_tools]
            logger.info(f"Available tools for query: {tool_names}")
            logger.info(f"Sending {len(messages)} messages to OpenAI")

        try:
            # Initial OpenAI API call
            response = self.openai.chat.completions.create(
                model=self.llm_config["model"],
                max_tokens=self.llm_config["max_tokens"],
                temperature=self.llm_config["temperature"],
                top_p=self.llm_config["top_p"],
                messages=messages,
                tools=available_tools,
                tool_choice="auto"
            )
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            error_message = f"Error processing query: {e}"
            return error_message

        # Process response and handle tool calls
        assistant_message = response.choices[0].message
        initial_response = assistant_message.content or ""
        
        # Process tool calls
        final_text = []
        tool_results = []

        tool_calls_metadata = {}
        if assistant_message.tool_calls:
            tool_calls_metadata = {
                "has_tool_calls": True,
                "tool_calls": assistant_message.tool_calls
            }
            if self.debug:
                logger.info(f"Processing {len(assistant_message.tool_calls)} tool calls")
                
            # Properly append assistant message with tool calls
            messages.append({
                "role": "assistant",
                "content": initial_response,  # This should be a string or null
                "tool_calls": assistant_message.tool_calls
            })
        # add the assistant message to history with tool calls metadata
        await self.add_message_to_history("assistant", initial_response, tool_calls_metadata)
        final_text.append(initial_response)
        if assistant_message.tool_calls:
            if self.debug:
                logger.info(f"Processing {len(assistant_message.tool_calls)} tool calls")
            
            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = tool_call.function.arguments
                # execute tool call
                if isinstance(tool_args, str):
                    try:
                        tool_args = json.loads(tool_args)
                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse tool arguments for {tool_name}: {tool_args}")
                        tool_args = {}
                if self.debug:
                    logger.info(f"Processing tool call: {tool_name} with args {tool_args}")
                # execute tool call on the server
                try:
                    for server_name, tools in self.available_tools.items():
                        tool_names = [tool.name for tool in tools]
                        if tool_name in tool_names:
                            result = await self.sessions[server_name]["session"].call_tool(tool_name, tool_args)
                            tool_content = result.content if hasattr(result, 'content') else str(result)
                            break
                    
                    # Handle the result content appropriately
                    if hasattr(tool_content, '__getitem__') and len(tool_content) > 0 and hasattr(tool_content[0], 'text'):
                        tool_content = tool_content[0].text
                    else:
                        tool_content = tool_content
                    tool_results.append(
                        {
                            "call": tool_name,
                            "result": tool_content
                        }
                    )
                    if self.debug:
                        result_preview = tool_content[:200] + "..." if len(str(tool_content)) > 200 else str(tool_content)
                        logger.info(f"Tool result preview: {result_preview}")
                    
                    # add the tool result to the messages
                    messages.append({
                        "role": "tool",
                        "content": str(tool_content),  # Ensure content is a string
                        "tool_call_id": tool_call.id
                    })
                    # add message to history
                    await self.add_message_to_history("tool", str(tool_content), {
                        "tool_call_id": tool_call.id,
                        "tool": tool_name,
                        "args": tool_args
                    })
                except Exception as e:
                    error_message = f"Error executing tool call {tool_name}: {e}"
                    logger.error(error_message)
                    # append the message regardless of error
                    messages.append({
                        "role": "tool",
                        "content": error_message,
                        "tool_call_id": tool_call.id
                    })
                    # add error message to history
                    await self.add_message_to_history("tool", error_message, {
                        "tool_call_id": tool_call.id,
                        "tool": tool_name,
                        "args": tool_args,
                        "error": True
                    })
                    final_text.append(f"\n[Error executing tool call {tool_name}: {error_message}]")
            if self.debug:
                logger.info("Getting final response from OpenAi with tool results")
            
            try:
                second_response = self.openai.chat.completions.create(
                    model=self.llm_config["model"],
                    max_tokens=self.llm_config["max_tokens"],
                    temperature=self.llm_config["temperature"],
                    top_p=self.llm_config["top_p"],
                    messages=messages
                )
                final_assistant_message = second_response.choices[0].message
                response_content = final_assistant_message.content or ""
                await self.add_message_to_history("assistant", response_content)
                final_text.append(response_content)
            except Exception as e:
                error_message = f"Error getting final response from OpenAI: {e}"
                logger.error(error_message)
                await self.add_message_to_history("assistant", error_message, {"error": True})
                final_text.append(f"\n[Error getting final response from OpenAI: {e}]")

        return "\n".join(final_text)

    def generate_system_prompt(self) -> str:
        """Generate a dynamic system prompt based on available tools and capabilities"""
        
        # Base prompt that's server-agnostic
        base_prompt = """You are an intelligent assistant with access to various tools and resources through the Model Context Protocol (MCP).

Your capabilities:
1. You can understand and process user queries
2. You can use available tools to fetch information and perform actions
3. You can access and summarize resources when needed

Guidelines:
1. Always verify tool availability before attempting to use them
2. Ask clarifying questions if the user's request is unclear
3. Explain your thought process before using any tools
4. If a requested capability isn't available, explain what's possible with current tools
5. Provide clear, concise responses focusing on the user's needs

Available Tools by Server:
"""

        # Add available tools dynamically
        tools_section = []
        for server_name, tools in self.available_tools.items():
            tools_section.append(f"\n[{server_name}]")
            for tool in tools:
                tool_desc = f"• {tool.name}: {tool.description}"
                # Add parameters if they exist
                if hasattr(tool, 'inputSchema') and tool.inputSchema:
                    params = tool.inputSchema.get('properties', {})
                    if params:
                        tool_desc += "\n  Parameters:"
                        for param_name, param_info in params.items():
                            param_desc = param_info.get('description', 'No description')
                            param_type = param_info.get('type', 'any')
                            tool_desc += f"\n    - {param_name} ({param_type}): {param_desc}"
                tools_section.append(tool_desc)

        interaction_guidelines = """
Before using any tool:
1. Analyze the user's request carefully
2. Check if the required tool is available in the current toolset
3. If unclear about the request or tool choice:
   - Ask for clarification from the user
   - Explain what information you need
   - Suggest available alternatives if applicable

When using tools:
1. Explain which tool you're going to use and why
2. Verify all required parameters are available
3. Handle errors gracefully and inform the user
4. Provide context for the results

Remember:
- Only use tools that are listed above
- Don't assume capabilities that aren't explicitly listed
- Be transparent about limitations
- Maintain a helpful and professional tone
"""

        # Combine all sections
        full_prompt = (
            base_prompt +
            "\n".join(tools_section) +
            interaction_guidelines
        )

        return full_prompt
