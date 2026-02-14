"""
Core assistant logic for LLM interaction and tool calling.
"""

import json
from typing import Awaitable, Callable, List, Optional

from openai import AsyncOpenAI

from ..config import config
from ..core.download import DownloadManager
from ..logger import logger
from .tools import get_assistant_tools, handle_tool_call


class AniAssistant:
    """Core assistant for interacting with LLM and executing tools."""

    def __init__(self, download_manager: DownloadManager):
        """Initialize assistant.

        Args:
            download_manager: DownloadManager instance for download operations
        """
        self.download_manager = download_manager
        self.client: Optional[AsyncOpenAI] = None
        self.model = config.llm.openai_model
        self.tools = get_assistant_tools()
        self.max_history = config.assistant.max_history_messages

        # Initialize OpenAI client
        if config.llm.openai_api_key:
            self.client = AsyncOpenAI(
                api_key=config.llm.openai_api_key,
                base_url=config.llm.openai_base_url,
                timeout=60.0,
            )
        else:
            logger.warning("OpenAI API key not set, assistant will not work")

        self.system_prompt = """You are a professional anime resource download assistant with access to several tools that you can combine to solve user requests.

## Available Tools:

1. **search_anime_resources**: Search for anime on websites (mikan/dmhy/acgrip)
2. **parse_rss**: Parse RSS feed to extract resource information and download links
3. **download_resource**: Download a single anime resource using its download URL
4. **execute_sql_query**: Query the download history database using SQL

## Database Schema:

Table: `resources`
- id: INTEGER PRIMARY KEY
- url: TEXT (download URL)
- title: TEXT (resource title)
- anime_name: TEXT (anime name)
- season: INTEGER (season number)
- episode: INTEGER (episode number)
- fansub: TEXT (fansub/subtitle group)
- quality: TEXT (quality like 1080p, 720p)
- languages: TEXT (language codes)
- version: INTEGER (version number)
- downloaded_at: TIMESTAMP (download timestamp)

## How to Compose Tools:

**Scenario 1: User provides RSS link**
1. Use `parse_rss` to extract resources from the RSS feed
2. For each resource you want to download, use `download_resource` with its URL

**Scenario 2: User wants to download but no URL**
1. Use `search_anime_resources` to find available resources
2. Identify the desired resource from search results
3. Use `download_resource` with the URL from search results

**Scenario 3: User asks about download history (e.g., "what's the latest episode?")**
1. Use `execute_sql_query` to query the database
2. The query tool supports pagination - results are paginated automatically
3. If you see "has_next_page: true" in the response, call the function again with the next page number to get more results
4. Example queries:
   - Latest episode: `SELECT anime_name, MAX(episode) as latest_ep, season, fansub, quality, downloaded_at FROM resources WHERE anime_name LIKE '%name%' GROUP BY anime_name ORDER BY downloaded_at DESC`
   - Recent downloads: `SELECT anime_name, season, episode, fansub, downloaded_at FROM resources ORDER BY downloaded_at DESC`
   - Specific anime: `SELECT * FROM resources WHERE anime_name LIKE '%name%' ORDER BY season, episode`
5. DO NOT add LIMIT or OFFSET to your SQL - pagination is handled automatically

**Scenario 4: User wants to download specific episode/fansub**
1. First search using `search_anime_resources` to see what's available
2. Analyze search results to find matching episode/fansub/quality
3. Use `download_resource` with the specific URL

## Important Guidelines:

- **Think step by step**: Break down complex requests into atomic tool calls
- **SQL queries**: When querying database, construct appropriate SQL SELECT statements
- **Database use**: The database contains all anime information known to the user and already downloaded. You can use this anime information (season, episode, etc.) to help determine the user's query and decide the actual download needs.
- **Search first**: If you don't have a download URL, search for it first
- **Parse RSS**: When user gives RSS link, parse it first to see what resources are available
- **Be smart**: Combine tools creatively to fulfill user requests
- **NEVER download resources marked as "✅ Downloaded"**: If search results show a resource is already downloaded, DO NOT attempt to download it again
- **Language**: Always respond in the same language as the user's message

Answer user questions in a friendly and professional manner."""

    async def process_message(
        self,
        user_message: str,
        history: Optional[List[dict]] = None,
        status_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> str:
        """Process user message and return response.

        Args:
            user_message: User's message
            history: Conversation history (list of message dicts with 'role' and 'content')
                    Should only include user/assistant messages from previous conversations
            status_callback: Optional callback to send status updates

        Returns:
            Assistant's response message
        """
        if not self.client:
            return (
                "❌ Assistant is not configured with OpenAI API key and cannot be used"
            )

        try:
            # Build messages with history
            messages = [{"role": "system", "content": self.system_prompt}]

            # Add conversation history (limit to max_history)
            # Only include user and assistant messages, filter out tool messages from history
            if history:
                filtered_history = [
                    msg
                    for msg in history[-self.max_history :]
                    if msg.get("role") in ["user", "assistant"]
                    and "tool_calls" not in msg
                ]
                messages.extend(filtered_history)

            # Add a separator comment to emphasize this is a new request
            # This helps the model focus on the current task rather than previous context
            if history:
                messages.append(
                    {
                        "role": "system",
                        "content": "--- New user request below. Focus on addressing THIS request specifically. Previous conversation is provided only for context. ---",
                    }
                )

            # Add current user message
            messages.append({"role": "user", "content": user_message})

            logger.info(f"Assistant: Processing message: {user_message}")

            if status_callback:
                await status_callback("🤔 正在思考...")

            # LLM interaction loop (support multiple tool calls)
            max_iterations = 20
            for iteration in range(max_iterations):
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=self.tools,
                    tool_choice="auto",
                )

                message = response.choices[0].message

                # If no tool calls, return the response
                if not message.tool_calls:
                    logger.info("Assistant: No tool calls, returning response")
                    if status_callback:
                        await status_callback("✍️ 正在整理回复...")
                    return message.content or "Sorry, I cannot understand your request"

                # Process tool calls
                messages.append(message)

                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                        logger.info(
                            f"Assistant: Calling tool {tool_name} with {arguments}"
                        )
                        # Send status update based on tool
                        if status_callback:
                            if (
                                tool_name == "download_resource"
                                and "title" in arguments
                            ):
                                status_msg = f"⬇️ 正在下载: {arguments['title']}"
                            else:
                                status_messages = {
                                    "search_anime_resources": "🔍 正在搜索动画资源...",
                                    "parse_rss": "📡 正在解析 RSS 订阅...",
                                    "execute_sql_query": "💾 正在查询下载历史数据库...",
                                }
                                status_msg = status_messages.get(
                                    tool_name, f"⚙️ 正在执行 {tool_name}..."
                                )
                            await status_callback(status_msg)
                        # Execute tool
                        tool_result = await handle_tool_call(
                            tool_name, arguments, self.download_manager
                        )
                    except json.JSONDecodeError:
                        error_msg = f"Failed to parse arguments for tool {tool_name}"
                        logger.error(
                            f"Assistant: {error_msg}: {tool_call.function.arguments}"
                        )
                        tool_result = (
                            f"Error: {error_msg}. Please check your arguments format."
                        )
                    except Exception as e:
                        error_msg = f"Error executing tool {tool_name}"
                        logger.exception(f"Assistant: {error_msg}")
                        tool_result = f"Error: {error_msg}: {str(e)}"

                    # Add tool result to messages
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": tool_result,
                        }
                    )

                    if not tool_result.startswith("Error"):
                        logger.info(
                            f"Assistant: Tool {tool_name} result: {tool_result[:200]}..."
                        )

            # If we exhausted iterations, ask LLM for final response
            logger.warning("Assistant: Max iterations reached, forcing final response")
            final_response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=None,  # Don't allow more tool calls
            )

            return (
                final_response.choices[0].message.content
                or "Operation completed but unable to generate response"
            )

        except Exception as e:
            logger.exception("Assistant: Error processing message")
            return f"❌ Error processing message: {str(e)}"
