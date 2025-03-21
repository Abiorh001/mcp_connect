from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.prompt import Prompt
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import box
from enum import Enum
from mcpomni_connect.client import MCPClient
from rich import print as rprint
from typing import Optional, Dict, Any
import json

class CommandType(Enum):
    """Command types for the MCP client"""
    HELP = "help"
    QUERY = "query"
    DEBUG = "debug"
    REFRESH = "refresh"
    TOOLS = "tools"
    RESOURCES = "resources"
    RESOURCE = "resource"
    PROMPTS = "prompts"
    PROMPT = "prompt"
    HISTORY = "history"
    CLEAR_HISTORY = "clear_history"
    SAVE_HISTORY = "save_history"
    QUIT = "quit"




class CommandHelp:
    """Help documentation for CLI commands"""
    
    @staticmethod
    def get_command_help(command_type: str) -> Dict[str, Any]:
        """Get detailed help for a specific command type"""
        help_docs = {
            "tools": {
                "description": "List and manage available tools across all connected servers",
                "usage": "/tools",
                "examples": [
                    "/tools  # List all available tools"
                ],
                "subcommands": {},
                "tips": [
                    "Tools are automatically discovered from connected servers",
                    "Use /debug to see more detailed tool information",
                    "Tools can be chained together for complex operations"
                ]
            },
            "prompts": {
                "description": "List and manage available prompts",
                "usage": "/prompts",
                "examples": [
                    "/prompts  # List all available prompts"
                ],
                "subcommands": {},
                "tips": [
                    "Prompts are discovered dynamically from servers",
                    "Each prompt may have different argument requirements",
                    "Use /help:prompt for detailed prompt usage"
                ]
            },
            "prompt": {
                "description": "Execute a specific prompt with arguments",
                "usage": "/prompt:<name>/<arguments>",
                "examples": [
                    "/prompt:weather/location=tokyo",
                    "/prompt:analyze/{\"data\":\"sample\",\"type\":\"full\"}",
                    "/prompt:search/query=test/limit=10"
                ],
                "subcommands": {},
                "tips": [
                    "Arguments can be provided in key=value format",
                    "Complex arguments can use JSON format",
                    "Use /prompts to see available prompts",
                    "Arguments are validated before execution",
                    "If a prompt does not have arguments, you can just use /prompt:<name>"
                ]
            },
            "resources": {
                "description": "List available resources across all servers",
                "usage": "/resources",
                "examples": [
                    "/resources  # List all available resources"
                ],
                "subcommands": {},
                "tips": [
                    "Resources are discovered from all connected servers",
                    "Use /resource:<uri> to access specific resources",
                    "Resources can be files, APIs, or other data sources"
                ]
            },
            "resource": {
                "description": "Access and analyze a specific resource",
                "usage": "/resource:<uri>",
                "examples": [
                    "/resource:file:///path/to/file",
                    "/resource:http://api.example.com/data"
                ],
                "subcommands": {},
                "tips": [
                    "URIs can be files, URLs, or other resource identifiers",
                    "Resources are automatically parsed based on type",
                    "Content is formatted for easy reading"
                ]
            },
            "debug": {
                "description": "Toggle debug mode for detailed information",
                "usage": "/debug",
                "examples": [
                    "/debug  # Toggle debug mode on/off"
                ],
                "subcommands": {},
                "tips": [
                    "Debug mode shows additional information",
                    "Useful for troubleshooting issues",
                    "Shows detailed server responses"
                ]
            },
            "refresh": {
                "description": "Refresh server capabilities and connections",
                "usage": "/refresh",
                "examples": [
                    "/refresh  # Refresh all server connections"
                ],
                "subcommands": {},
                "tips": [
                    "Use when adding new servers",
                    "Updates tool and prompt listings",
                    "Reconnects to disconnected servers"
                ]
            },
            "help": {
                "description": "Get help on available commands",
                "usage": "/help or /help:<command>",
                "examples": [
                    "/help  # Show all commands",
                    "/help:prompt  # Show prompt help",
                    "/help:tools  # Show tools help"
                ],
                "subcommands": {},
                "tips": [
                    "Use /help for general overview",
                    "Get detailed help with /help:<command>",
                    "Examples show common usage patterns"
                ]
            },
            "history": {
                "description": "Show the message history",
                "usage": "/history",
                "examples": [
                    "/history  # Show the message history"
                ],
                "subcommands": {},
                "tips": [
                    "Use to see the message history"
                ]
            },
            "clear_history": {
                "description": "Clear the message history",
                "usage": "/clear_history",
                "examples": [
                    "/clear_history  # Clear the message history"
                ],
                "subcommands": {},
                "tips": [
                    "Use to clear the message history"
                ]
            },
            "save_history": {
                "description": "Save the message history to a file",
                "usage": "/save_history:path/to/file",
                "examples": [
                    "/save_history:path/to/file  # Save the message history to a file"
                ],
                "subcommands": {},
                "tips": [
                    "Use to save the message history to a file"
                ]
            }
        }
        return help_docs.get(command_type, {})


class MCPClientCLI:
    def __init__(self, client: MCPClient):
        self.client = client
        self.console = Console()
        self.command_help = CommandHelp()
    def parse_command(self, input_text: str) -> tuple[CommandType, str]:
        """Parse input to determine command type and payload"""
        input_text = input_text.strip().lower()
        
        if input_text == 'quit':
            return CommandType.QUIT, ""
        elif input_text == '/debug':
            return CommandType.DEBUG, ""
        elif input_text == '/refresh':
            return CommandType.REFRESH, ""
        elif input_text == '/help':
            return CommandType.HELP, ""
        elif input_text.startswith('/help:'):
            return CommandType.HELP, input_text[6:].strip()
        elif input_text == '/tools':
            return CommandType.TOOLS, ""
        elif input_text == '/resources':
            return CommandType.RESOURCES, ""
        elif input_text == '/prompts':
            return CommandType.PROMPTS, ""
        elif input_text.startswith('/resource:'):
            return CommandType.RESOURCE, input_text[10:].strip()
        elif input_text.startswith('/prompt:'):
            return CommandType.PROMPT, input_text[8:].strip()
        elif input_text == '/history':
            return CommandType.HISTORY, ""
        elif input_text == '/clear_history':
            return CommandType.CLEAR_HISTORY, ""
        elif input_text.startswith('/save_history:'):
            return CommandType.SAVE_HISTORY, input_text[14:].strip()
        else:
            if input_text:
                return CommandType.QUERY, input_text
            else:
                return None, None

    async def handle_debug_command(self, input_text: str=""):
        """Handle debug toggle command"""
        self.client.debug = not self.client.debug
        self.console.print(
            f"[{'green' if self.client.debug else 'red'}]Debug mode "
            f"{'enabled' if self.client.debug else 'disabled'}[/]"
        )

    async def handle_refresh_command(self, input_text: str=""):
        """Handle refresh capabilities command"""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True
        ) as progress:
            progress.add_task("Refreshing capabilities...", total=None)
            await self.client.refresh_capabilities()
        self.console.print("[green]Capabilities refreshed successfully[/]")
    

    async def handle_help_command(self, command_type: Optional[str] = None):
        """Show help information for commands"""
        if command_type:
            # Show specific command help
            help_info = self.command_help.get_command_help(command_type.lower())
            if help_info:
                panel = Panel(
                    f"[bold cyan]{command_type.upper()}[/]\n\n"
                    f"[bold white]Description:[/]\n{help_info['description']}\n\n"
                    f"[bold white]Usage:[/]\n{help_info['usage']}\n\n"
                    f"[bold white]Examples:[/]\n" + "\n".join(help_info['examples']) + "\n\n"
                    f"[bold white]Tips:[/]\n" + "\n".join(f"• {tip}" for tip in help_info['tips']),
                    title="[bold blue]Command Help[/]",
                    border_style="blue"
                )
                self.console.print(panel)
            else:
                self.console.print(f"[red]No help available for command: {command_type}[/]")
        else:
            # Show general help with all commands
            help_table = Table(
                title="[bold blue]Available Commands[/]",
                box=box.ROUNDED,
                show_header=True,
                header_style="bold cyan"
            )
            help_table.add_column("Command", style="cyan")
            help_table.add_column("Description", style="white")
            help_table.add_column("Usage", style="green")

            for cmd_type in CommandType:
                help_info = self.command_help.get_command_help(cmd_type.value)
                if help_info:
                    help_table.add_row(
                        f"/{cmd_type.value}",
                        help_info['description'],
                        help_info['usage']
                    )

            self.console.print(help_table)
            
            # Show general tips
            tips_panel = Panel(
                "• Use [cyan]/help:<command>[/] for detailed help on specific commands\n"
                "• Commands are case-insensitive\n"
                "• Use [cyan]quit[/] to exit the application\n"
                "• Enable debug mode with [cyan]/debug[/] for more information",
                title="[bold yellow]💡 Tips[/]",
                border_style="yellow"
            )
            self.console.print(tips_panel)


    async def handle_tools_command(self, input_text: str=""):
        """Handle tools listing command"""
        tools = await self.client.list_tools()
        tools_table = Table(title="Available Tools", box=box.ROUNDED)
        tools_table.add_column("Tool", style="cyan", no_wrap=False)
        tools_table.add_column("Description", style="green", no_wrap=False)
        
        for tool in tools:
            tools_table.add_row(
                tool.name,
                tool.description or "No description available"
            )
        self.console.print(tools_table)

    async def handle_resources_command(self, input_text: str=""):
        """Handle resources listing command"""
        resources = await self.client.list_resources()
        resources_table = Table(title="Available Resources", box=box.ROUNDED)
        resources_table.add_column("URI", style="cyan", no_wrap=False)
        resources_table.add_column("Name", style="blue")
        resources_table.add_column("Description", style="green", no_wrap=False)
        
        for resource in resources:
            resources_table.add_row(
                str(resource.uri),
                resource.name,
                resource.description or "No description available"
            )
        self.console.print(resources_table)
    
    async def handle_prompts_command(self, input_text: str=""):
        """Handle prompts listing command"""
        prompts = await self.client.list_prompts()
        prompts_table = Table(title="Available Prompts", box=box.ROUNDED)
        prompts_table.add_column("Name", style="cyan", no_wrap=False)
        prompts_table.add_column("Description", style="blue")
        prompts_table.add_column("Arguments", style="green")
        
        if not prompts:
            self.console.print("[yellow]No prompts available[/yellow]")
            return
            
        for prompt in prompts:
            # Safely handle None values and ensure string conversion
            name = str(prompt.name) if hasattr(prompt, 'name') and prompt.name else "Unnamed Prompt"
            description = str(prompt.description) if hasattr(prompt, 'description') and prompt.description else "No description available"
            arguments = prompt.arguments
            arguments_str = ""
            if hasattr(prompt, 'arguments') and prompt.arguments:
                for arg in arguments:
                    arg_name = arg.name
                    arg_description = arg.description
                    required = arg.required
                    arguments_str += f"{arg_name}: {arg_description} ({'required' if required else 'optional'})\n"
            else:
                arguments_str = "No arguments available"
            
            prompts_table.add_row(name, description, arguments_str)
            
        self.console.print(prompts_table)
    
    async def handle_resource_command(self, uri: str):
        """Handle resource reading command"""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True
        ) as progress:
            progress.add_task("Loading resource...", total=None)
            content = await self.client.read_resource(uri)
        
        if content.startswith("```") or content.startswith("#"):
            self.console.print(Markdown(content))
        else:
            self.console.print(Panel(content, title=uri, border_style="blue"))

    async def handle_prompt_command(self, input_text: str):
        """Handle prompt reading command"""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True
        ) as progress:
            progress.add_task("Loading prompt...", total=None)
            name, arguments = self.parse_prompt_command(input_text)
            content = await self.client.get_prompt(name, arguments)
        
        if content.startswith("```") or content.startswith("#"):
            self.console.print(Markdown(content))
        else:
            self.console.print(Panel(content, title=name, border_style="blue"))
    
    def parse_prompt_command(self, input_text: str) -> tuple[str, Optional[dict]]:
        """Parse prompt command to determine name and arguments.
        
        Supports multiple formats:
        1. /prompt:name/{key1:value1,key2:value2}  # JSON-like format
        2. /prompt:name/key1=value1/key2=value2    # Key-value pair format
        3. /prompt:name                            # No arguments
        
        Args:
            input_text: The command text to parse
            
        Returns:
            Tuple of (prompt_name, arguments_dict)
            
        Raises:
            ValueError: If the command format is invalid
        """
        input_text = input_text.strip()
        
        # Split into name and arguments parts
        parts = input_text.split('/', 1)
        name = parts[0].strip()
        
        if len(parts) == 1:
            return name, None
            
        args_str = parts[1].strip()
        
        # Try parsing as JSON-like format first
        if args_str.startswith('{') and args_str.endswith('}'):
            try:
                # Convert single quotes to double quotes for JSON parsing
                args_str = args_str.replace("'", '"')
                arguments = json.loads(args_str)
                # Convert all values to strings
                return name, {k: str(v) for k, v in arguments.items()}
            except json.JSONDecodeError:
                pass
                
        # Try parsing as key-value pairs
        arguments = {}
        try:
            # Split by / and handle each key-value pair
            for pair in args_str.split('/'):
                if '=' not in pair:
                    raise ValueError(f"Invalid argument format: {pair}")
                key, value = pair.split('=', 1)
                key = key.strip()
                value = value.strip()
                arguments[key] = value
                
            return name, arguments
        except Exception as e:
            raise ValueError(f"Invalid argument format. Use either:\n"
                           f"1. /prompt:name/{{key1:value1,key2:value2}}\n"
                           f"2. /prompt:name/key1=value1/key2=value2\n"
                           f"Error: {str(e)}")

    async def handle_query(self, query: str):
        """Handle general query processing"""
        if not query or query.isspace():
            return

        # Parse the command first
        cmd_type, payload = self.parse_command(query)
        if not cmd_type:
            return
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True
        ) as progress:
            progress.add_task("Processing query...", total=None)
            response = await self.client.process_query(query)
        
        if "```" in response or "#" in response:
            self.console.print(Markdown(response))
        else:
            self.console.print(Panel(response, border_style="green"))
    
    async def handle_history_command(self, input_text: str=""):
        """Handle history command"""
        prompts_table = Table(title="Message History", box=box.ROUNDED)
        prompts_table.add_column("Role", style="cyan", no_wrap=False)
        prompts_table.add_column("Content", style="green")
        for message in self.client.message_history:
            prompts_table.add_row(message['role'], message['content'])
        self.console.print(prompts_table)


    async def handle_clear_history_command(self, input_text: str=""):
        """Handle clear history command"""
        await self.client.clear_history()
        self.console.print("[green]Message history cleared[/]")
    async def handle_save_history_command(self, input_text: str):
        """Handle save history command"""
        await self.client.save_message_history_to_file(input_text)
        self.console.print(f"[green]Message history saved to {input_text}[/]")
    async def chat_loop(self):
        """Run an interactive chat loop with rich UI"""
        self.print_welcome_header()

        # Command handlers mapping
        handlers = {
            CommandType.DEBUG: self.handle_debug_command,
            CommandType.REFRESH: self.handle_refresh_command,
            CommandType.HELP: self.handle_help_command,
            CommandType.TOOLS: self.handle_tools_command,
            CommandType.RESOURCES: self.handle_resources_command,
            CommandType.RESOURCE: self.handle_resource_command,
            CommandType.QUERY: self.handle_query,
            CommandType.PROMPTS: self.handle_prompts_command,
            CommandType.PROMPT: self.handle_prompt_command,
            CommandType.HISTORY: self.handle_history_command,
            CommandType.CLEAR_HISTORY: self.handle_clear_history_command,
            CommandType.SAVE_HISTORY: self.handle_save_history_command
        }

        while True:
            try:
                query = Prompt.ask("\n[bold blue]Query[/]").strip()
                # get the command type and payload from the query
                command_type, payload = self.parse_command(query)

                if command_type == CommandType.QUIT:
                    break

                # get the handler for the command type from the handlers mapping
                handler = handlers.get(command_type)
                if handler:
                    await handler(payload)
            except KeyboardInterrupt:
                self.console.print("[yellow]Shutting down client...[/]", style="yellow")
                break
            except Exception as e:
                self.console.print(f"[red]Error:[/] {str(e)}", style="bold red")

        # Shutdown message
        self.console.print(Panel(
            "[yellow]Shutting down client...[/]",
            border_style="yellow",
            box=box.DOUBLE
        ))

    def print_welcome_header(self):
        ascii_art = """[bold blue]
    ╔═══════════════════════════════════════════════════════════════════════════╗
    ║  ███╗   ███╗ ██████╗██████╗     ██████╗ ███╗   ███╗███╗   ██╗██╗       ║
    ║  ████╗ ████║██╔════╝██╔══██╗   ██╔═══██╗████╗ ████║████╗  ██║██║       ║
    ║  ██╔████╔██║██║     ██████╔╝   ██║   ██║██╔████╔██║██╔██╗ ██║██║       ║
    ║  ██║╚██╔╝██║██║     ██╔═══╝    ██║   ██║██║╚██╔╝██║██║╚██╗██║██║       ║
    ║  ██║ ╚═╝ ██║╚██████╗██║        ╚██████╔╝██║ ╚═╝ ██║██║ ╚████║██║       ║
    ║  ╚═╝     ╚═╝ ╚═════╝╚═╝         ╚═════╝ ╚═╝     ╚═╝╚═╝  ╚═══╝╚═╝       ║
    ║                                                                           ║
    ║     [cyan]Model[/] · [cyan]Context[/] · [cyan]Protocol[/]  →  [green]OMNI CONNECT[/]              ║
    ╚═══════════════════════════════════════════════════════════════════════════╝[/]
    """
        
        # Server status with emojis and cool styling
        server_status = [f"[bold green]●[/] [cyan]{name}[/]" for name in self.client.server_names]
        
        content = f"""
{ascii_art}

[bold magenta]🚀 Universal MCP Client[/]

[bold white]Connected Servers:[/]
{' | '.join(server_status)}

[dim]▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰[/]
[cyan]Your Universal Gateway to MCP Servers[/]
[dim]▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰[/]
"""
        
        # Add some flair with a fancy border
        self.console.print(Panel(
            content,
            title="[bold blue]⚡ MCPOmni Connect ⚡[/]",
            subtitle="[bold cyan]v0.1.0[/]",
            border_style="blue",
            box=box.DOUBLE_EDGE
        ))

        # Command list with emojis and better styling
        commands_table = Table(
            title="[bold magenta]Available Commands[/]",
            box=box.SIMPLE_HEAD,
            border_style="bright_blue"
        )
        commands_table.add_column("[bold cyan]Command[/]", style="cyan")
        commands_table.add_column("[bold green]Description[/]", style="green")
        commands_table.add_column("[bold yellow]Example[/]", style="yellow")
        
        commands = [
            ("/debug", "Toggle debug mode 🐛", ""),
            ("/refresh", "Refresh server capabilities 🔄", ""),
            ("/help", "Show help 🆘", "/help:command"),
            ("/history", "Show message history 📝", ""),
            ("/clear_history", "Clear message history 🧹", ""),
            ("/save_history", "Save message history to file 💾", "/save_history:path/to/file"),
            ("/tools", "List available tools 🔧", ""),
            ("/resources", "List available resources 📚", ""),
            ("/resource:<uri>", "Read a specific resource 🔍", "/resource:file:///path/to/file"),
            ("/prompts", "List available prompts 💬", ""),
            ("/prompt:<name>/<args>", "Read a prompt with arguments or without arguments 💬", "/prompt:weather/location=lagos/radius=2"),
            ("quit", "Exit the application 👋", "")
        ]
        
        for cmd, desc, example in commands:
            commands_table.add_row(cmd, desc, example)
        
        self.console.print(commands_table)
        
        # Add a note about prompt arguments
        self.console.print(Panel(
            "[bold yellow]📝 Prompt Arguments:[/]\n"
            "• Use [cyan]key=value[/] pairs separated by [cyan]/[/]\n"
            "• Or use [cyan]{key:value}[/] JSON-like format\n"
            "• Values are automatically converted to appropriate types\n"
            "• Use [cyan]/prompts[/] to see available prompts and their arguments",
            title="[bold blue]💡 Tip[/]",
            border_style="blue",
            box=box.ROUNDED
        ))
