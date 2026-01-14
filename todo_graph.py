"""
LangGraph workflow for processing natural language todo commands using reactive tool calling
"""
from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages
from langchain_ollama import ChatOllama
from langchain_core.tools import tool
from langchain.agents import create_agent
from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
import json
import os
from datetime import datetime

# JSON database file - use absolute path based on script location
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "todos.json")

# Define the state - simplified for reactive tool calling
class TodoAgentState(TypedDict):
    messages: Annotated[list, add_messages]

# Database functions
def load_todos():
    """Load todos from JSON file"""
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def save_todos(todos):
    """Save todos to JSON file"""
    with open(DB_FILE, 'w') as f:
        json.dump(todos, f, indent=2)

def get_next_id(todos):
    """Get the next available ID"""
    if not todos:
        return 1
    return max(todo.get('id', 0) for todo in todos) + 1

# Tool functions for todo operations
@tool
def create_todo_tool(text: str) -> dict:
    """Create a new todo item with the given text."""
    todos = load_todos()
    new_todo = {
        "id": get_next_id(todos),
        "text": text,
        "completed": False,
        "created_at": datetime.now().isoformat()
    }
    todos.append(new_todo)
    save_todos(todos)
    return {"success": True, "todo": new_todo, "message": f"Created todo: {text}"}

@tool
def delete_todo_tool(todo_id: int) -> dict:
    """Delete a todo item by its ID."""
    todos = load_todos()
    todo = next((t for t in todos if t['id'] == todo_id), None)
    if not todo:
        return {"success": False, "message": f"Todo with ID {todo_id} not found"}
    
    todos = [t for t in todos if t['id'] != todo_id]
    save_todos(todos)
    return {"success": True, "message": f"Deleted todo: {todo['text']}"}

@tool
def update_todo_tool(todo_id: int, new_text: str) -> dict:
    """Update the text of a todo item by its ID."""
    todos = load_todos()
    todo = next((t for t in todos if t['id'] == todo_id), None)
    if not todo:
        return {"success": False, "message": f"Todo with ID {todo_id} not found"}
    
    old_text = todo['text']
    todo['text'] = new_text
    save_todos(todos)
    return {"success": True, "message": f"Updated todo {todo_id} from '{old_text}' to '{new_text}'"}

@tool
def complete_todo_tool(todo_id: int) -> dict:
    """Mark a todo item as completed by its ID."""
    todos = load_todos()
    todo = next((t for t in todos if t['id'] == todo_id), None)
    if not todo:
        return {"success": False, "message": f"Todo with ID {todo_id} not found"}
    
    todo['completed'] = True
    save_todos(todos)
    return {"success": True, "message": f"Marked todo as completed: {todo['text']}"}

@tool
def delete_all_todos_tool() -> dict:
    """Delete all todo items."""
    save_todos([])
    return {"success": True, "message": "All todos deleted"}

@tool
def list_todos_tool() -> dict:
    """Get all todos."""
    todos = load_todos()
    return {"success": True, "todos": todos, "count": len(todos)}

# Initialize tools
tools = [
    create_todo_tool,
    delete_todo_tool,
    update_todo_tool,
    complete_todo_tool,
    delete_all_todos_tool,
    list_todos_tool
]

# Initialize LLM
llm = ChatOllama(model="llama3.2:latest")

# Create the ReAct agent with the LLM and tools (handles reactive tool calling)
agent = create_agent(llm, tools)

# Use ToolNode for automatic tool execution
tool_node = ToolNode(tools)

# Agent node - calls LLM which can decide to use tools
def call_agent(state: TodoAgentState) -> TodoAgentState:
    """Agent node that processes user command and decides to call tools"""
    messages = state["messages"]
    
    # Get current todos for context
    todos = load_todos()
    todos_context = "\n".join([f"ID {t['id']}: {t['text']} ({'completed' if t.get('completed') else 'pending'})" 
                               for t in todos])
    
    # Add system context if this is the first message
    if len(messages) == 1 and todos:
        system_msg = f"""You are a helpful todo assistant. Current todos:
{todos_context}

When the user asks about todos by text (not ID), find the matching ID from the list above.
Always use the appropriate tool to perform actions."""
        # Prepend system message
        messages = [("system", system_msg)] + messages
    
    # Call agent with messages dict - create_agent handles reactive tool calling
    result = agent.invoke({"messages": messages})
    
    # Extract new messages from result (agent may have added tool calls and responses)
    new_messages = result.get("messages", [])
    
    return {"messages": new_messages}

# Conditional edge function - check if agent wants to call tools
def should_continue(state: TodoAgentState) -> str:
    """Check if the agent wants to call tools or is done"""
    last_message = state["messages"][-1]
    
    # If the last message has tool calls, route to tools
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "tools"
    
    # Otherwise, we're done
    return "__end__"

# Build the graph with reactive tool calling
def create_todo_graph():
    """Create and compile the todo command processing graph with reactive tool calling"""
    workflow = StateGraph(TodoAgentState)
    
    # Add nodes
    workflow.add_node("agent", call_agent)  # LLM agent node
    workflow.add_node("tools", tool_node)   # Automatic tool execution node
    
    # Set entry point
    workflow.add_edge(START, "agent")
    
    # Conditional edge: check if agent wants to call tools
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",      # If tools called, go to tools node
            "__end__": END         # Otherwise, end
        }
    )
    
    # After tools execute, loop back to agent to process results
    workflow.add_edge("tools", "agent")
    
    # Add memory
    memory = MemorySaver()
    
    # Compile the graph
    app = workflow.compile(checkpointer=memory)
    
    return app

# Global graph instance
_todo_graph = None

def get_todo_graph():
    """Get or create the todo graph instance"""
    global _todo_graph
    if _todo_graph is None:
        _todo_graph = create_todo_graph()
    return _todo_graph

def process_command_with_graph(command: str, thread_id: str = "default") -> dict:
    """Process a natural language command using LangGraph with reactive tool calling"""
    from langchain_core.messages import ToolMessage
    
    graph = get_todo_graph()
    
    # Create initial state with user message
    initial_state = {
        "messages": [("user", command)]
    }
    
    # Configuration with thread_id for memory
    config = {"configurable": {"thread_id": thread_id}}
    
    # Run the graph - it will reactively call tools as needed
    final_state = graph.invoke(initial_state, config)
    
    # Extract result from tool messages or final agent response
    result = {"success": False, "message": "No result"}
    
    # Look for ToolMessage objects (results from tool execution)
    for msg in reversed(final_state["messages"]):
        # Check if this is a ToolMessage (result from tool execution)
        if isinstance(msg, ToolMessage):
            # ToolMessage content contains the tool result
            tool_result = msg.content
            
            # Tool results are typically dicts (from our tool functions)
            if isinstance(tool_result, dict):
                result = tool_result
                break
            elif isinstance(tool_result, str):
                # Try to parse JSON string
                try:
                    import json
                    parsed = json.loads(tool_result)
                    if isinstance(parsed, dict):
                        result = parsed
                        break
                except:
                    result = {"success": True, "message": tool_result}
                    break
    
    # If no tool result found, use the final agent response
    if not result.get("success"):
        final_message = final_state["messages"][-1]
        if hasattr(final_message, 'content'):
            content = final_message.content
            # Check if agent mentions success in response
            if isinstance(content, str):
                result = {"success": True, "message": content}
            else:
                result = {"success": True, "message": str(content)}
    
    return result
