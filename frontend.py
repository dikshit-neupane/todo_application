import streamlit as st
import requests
from typing import List, Dict
import time

# API base URL
API_URL = "http://localhost:8000"

# Page config
st.set_page_config(
    page_title="Todo App",
    page_icon="✅",
    layout="wide"
)

# Custom CSS for modern UI
st.markdown("""
    <style>
    .main {
        padding: 2rem;
    }
    .stTextInput > div > div > input {
        font-size: 1.1rem;
        padding: 0.75rem;
    }
    .todo-item {
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
        background-color: #f8f9fa;
    }
    .todo-completed {
        opacity: 0.6;
        text-decoration: line-through;
        border-left-color: #28a745;
    }
    .todo-header {
        font-size: 2rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 2rem;
    }
    </style>
""", unsafe_allow_html=True)

def get_todos() -> List[Dict]:
    """Fetch all todos from API"""
    try:
        response = requests.get(f"{API_URL}/todos")
        if response.status_code == 200:
            return response.json()
        return []
    except requests.exceptions.ConnectionError:
        st.error("⚠️ Cannot connect to backend API. Please make sure the FastAPI server is running on port 8000.")
        return []
    except Exception as e:
        st.error(f"Error fetching todos: {str(e)}")
        return []

def create_todo(text: str) -> bool:
    """Create a new todo"""
    try:
        response = requests.post(f"{API_URL}/todos", json={"text": text})
        return response.status_code == 200
    except Exception as e:
        st.error(f"Error creating todo: {str(e)}")
        return False

def update_todo(todo_id: int, text: str = None, completed: bool = None) -> bool:
    """Update a todo"""
    try:
        data = {}
        if text is not None:
            data["text"] = text
        if completed is not None:
            data["completed"] = completed
        response = requests.put(f"{API_URL}/todos/{todo_id}", json=data)
        return response.status_code == 200
    except Exception as e:
        st.error(f"Error updating todo: {str(e)}")
        return False

def delete_todo(todo_id: int) -> bool:
    """Delete a todo"""
    try:
        response = requests.delete(f"{API_URL}/todos/{todo_id}")
        return response.status_code == 200
    except Exception as e:
        st.error(f"Error deleting todo: {str(e)}")
        return False

def delete_all_todos() -> bool:
    """Delete all todos"""
    try:
        response = requests.delete(f"{API_URL}/todos")
        return response.status_code == 200
    except Exception as e:
        st.error(f"Error deleting all todos: {str(e)}")
        return False

def process_command(command: str, thread_id: str = "default") -> Dict:
    """Process natural language command using LangGraph"""
    try:
        response = requests.post(
            f"{API_URL}/todos/process-command",
            params={"command": command, "thread_id": thread_id}
        )
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        st.error(f"Error processing command: {str(e)}")
        return None

def main():
    st.markdown('<div class="todo-header">Todo App</div>', unsafe_allow_html=True)
    
    # Initialize session state
    if 'refresh' not in st.session_state:
        st.session_state.refresh = False
    
    # Prompt input field
    st.markdown("**Examples:** `Add buy groceries`, `Remove todo 1`, `Complete todo 2`, `Edit todo 3 to buy milk`, `Delete all`")
    
    col1, col2 = st.columns([4, 1])
    
    with col1:
        prompt = st.text_input(
            "Command",
            placeholder="",
            label_visibility="collapsed"
        )
    
    with col2:
        submit_button = st.button("Execute", type="primary", use_container_width=True)
    
    # Process command
    if submit_button and prompt:
        result = process_command(prompt)
        
        if result:
            graph_result = result.get("result", {})
            message = result.get("message", graph_result.get("message", ""))
            success = graph_result.get("success", False)
            
            if success:
                # Show success message from LangGraph
                if "Created" in message or "created" in message:
                    st.success(f"✅ {message}")
                elif "Deleted" in message or "deleted" in message:
                    st.success(f"🗑️ {message}")
                elif "Updated" in message or "updated" in message:
                    st.success(f"✏️ {message}")
                elif "completed" in message.lower():
                    st.success(f"✅ {message}")
                elif "todos" in graph_result:
                    # List action - show todos
                    todos_list = graph_result.get("todos", [])
                    st.info(f"📋 Found {len(todos_list)} todos")
                else:
                    st.success(f"✅ {message}")
                st.session_state.refresh = True
            else:
                st.warning(f"⚠️ {message}")
        
        time.sleep(0.5)
        st.rerun()
    
    # Display todos
    st.markdown("---")
    st.markdown("### 📋 Your Todos")
    
    todos = get_todos()
    
    if not todos:
        st.info("No todos yet. Add one using the command field above!")
    else:
        # Stats
        total = len(todos)
        completed = sum(1 for t in todos if t.get('completed', False))
        
        
        st.markdown("---")
        
        # Display todos
        for todo in todos:
            todo_id = todo['id']
            todo_text = todo['text']
            completed = todo.get('completed', False)
            
            # Create columns for todo display
            col1, col2, col3, col4 = st.columns([6, 1, 1, 1])
            
            with col1:
                status_icon = "✅" if completed else "⏳"
                status_class = "todo-completed" if completed else ""
                st.markdown(f"""
                    <div class="todo-item {status_class}">
                        <strong>{status_icon} Todo #{todo_id}:</strong> {todo_text}
                    </div>
                """, unsafe_allow_html=True)
            
            with col2:
                if not completed:
                    if st.button("✓", key=f"complete_{todo_id}", help="Mark as complete"):
                        if update_todo(todo_id, completed=True):
                            st.success("Completed!")
                            time.sleep(0.5)
                            st.rerun()
                else:
                    if st.button("↩", key=f"uncomplete_{todo_id}", help="Mark as incomplete"):
                        if update_todo(todo_id, completed=False):
                            st.success("Marked as incomplete!")
                            time.sleep(0.5)
                            st.rerun()
            
            with col3:
                if st.button("✏️", key=f"edit_{todo_id}", help="Edit"):
                    st.session_state[f"editing_{todo_id}"] = True
            
            with col4:
                if st.button("🗑️", key=f"delete_{todo_id}", help="Delete"):
                    if delete_todo(todo_id):
                        st.success("Deleted!")
                        time.sleep(0.5)
                        st.rerun()
            
            # Edit form
            if st.session_state.get(f"editing_{todo_id}", False):
                with st.form(key=f"edit_form_{todo_id}"):
                    new_text = st.text_input("Edit todo", value=todo_text, key=f"edit_input_{todo_id}")
                    col_submit, col_cancel = st.columns(2)
                    with col_submit:
                        submit_edit = st.form_submit_button("Save")
                    with col_cancel:
                        cancel_edit = st.form_submit_button("Cancel")
                    
                    if submit_edit and new_text:
                        if update_todo(todo_id, text=new_text):
                            st.session_state[f"editing_{todo_id}"] = False
                            st.success("Updated!")
                            time.sleep(0.5)
                            st.rerun()
                    
                    if cancel_edit:
                        st.session_state[f"editing_{todo_id}"] = False
                        st.rerun()
            
            st.markdown("<br>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
