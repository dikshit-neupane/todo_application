from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import json
import os
from datetime import datetime

# Lazy import to avoid startup errors if dependencies are missing
def get_process_command_function():
    """Lazy import of process_command_with_graph"""
    try:
        from todo_graph import process_command_with_graph
        return process_command_with_graph
    except ImportError as e:
        raise ImportError(
            f"Failed to import todo_graph. Make sure all dependencies are installed: {e}\n"
            "Run: uv sync or pip install langchain langchain-ollama langgraph"
        )

app = FastAPI(title="Todo API")

# Enable CORS for Streamlit
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# JSON database file - use absolute path based on script location
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "todos.json")

class Todo(BaseModel):
    id: int
    text: str
    completed: bool = False
    created_at: str

class TodoCreate(BaseModel):
    text: str

class TodoUpdate(BaseModel):
    text: Optional[str] = None
    completed: Optional[bool] = None

def load_todos() -> List[dict]:
    """Load todos from JSON file"""
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def save_todos(todos: List[dict]):
    """Save todos to JSON file"""
    with open(DB_FILE, 'w') as f:
        json.dump(todos, f, indent=2)

def get_next_id(todos: List[dict]) -> int:
    """Get the next available ID"""
    if not todos:
        return 1
    return max(todo.get('id', 0) for todo in todos) + 1

@app.get("/")
def read_root():
    return {"message": "Todo API is running"}

@app.get("/todos", response_model=List[Todo])
def get_todos():
    """Get all todos"""
    todos = load_todos()
    return todos

@app.post("/todos", response_model=Todo)
def create_todo(todo: TodoCreate):
    """Create a new todo"""
    todos = load_todos()
    new_todo = {
        "id": get_next_id(todos),
        "text": todo.text,
        "completed": False,
        "created_at": datetime.now().isoformat()
    }
    todos.append(new_todo)
    save_todos(todos)
    return new_todo

@app.get("/todos/{todo_id}", response_model=Todo)
def get_todo(todo_id: int):
    """Get a specific todo by ID"""
    todos = load_todos()
    todo = next((t for t in todos if t['id'] == todo_id), None)
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    return todo

@app.put("/todos/{todo_id}", response_model=Todo)
def update_todo(todo_id: int, todo_update: TodoUpdate):
    """Update a todo"""
    todos = load_todos()
    todo = next((t for t in todos if t['id'] == todo_id), None)
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    
    if todo_update.text is not None:
        todo['text'] = todo_update.text
    if todo_update.completed is not None:
        todo['completed'] = todo_update.completed
    
    save_todos(todos)
    return todo

@app.delete("/todos/{todo_id}")
def delete_todo(todo_id: int):
    """Delete a todo"""
    todos = load_todos()
    todo = next((t for t in todos if t['id'] == todo_id), None)
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    
    todos = [t for t in todos if t['id'] != todo_id]
    save_todos(todos)
    return {"message": "Todo deleted successfully"}

@app.delete("/todos")
def delete_all_todos():
    """Delete all todos"""
    save_todos([])
    return {"message": "All todos deleted successfully"}

@app.post("/todos/process-command")
def process_command(command: str, thread_id: str = "default"):
    """Process natural language command using LangGraph and return action result"""
    try:
        # Lazy import to avoid startup errors
        process_command_with_graph = get_process_command_function()
        # Use LangGraph to process the command
        result = process_command_with_graph(command, thread_id)
        
        # Extract action information from result for backward compatibility
        action = None
        todo_id = None
        todo_text = None
        
        if result.get("success"):
            message = result.get("message", "")
            message_lower = message.lower()
            
            # Determine action from result message
            if "created" in message_lower or "create" in message_lower:
                action = "create"
                if "todo" in result:
                    todo_text = result["todo"].get("text")
            elif "deleted" in message_lower and "all" in message_lower:
                action = "delete_all"
            elif "deleted" in message_lower:
                action = "delete"
            elif "updated" in message_lower:
                action = "update"
            elif "completed" in message_lower:
                action = "complete"
            elif "todos" in result:
                action = "list"
        
        return {
            "action": action,
            "todo_id": todo_id,
            "todo_text": todo_text,
            "result": result,
            "message": result.get("message", "")
        }
    except Exception as e:
        return {
            "action": None,
            "todo_id": None,
            "todo_text": None,
            "result": {"success": False, "message": f"Error processing command: {str(e)}"},
            "message": f"Error: {str(e)}"
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
