from typing import Dict, Optional
import uuid

state_store: Dict[str, dict] = {}

def create_state(initial_state: dict) -> str:
    session_id = str(uuid.uuid4())
    state_store[session_id] = initial_state
    return session_id

def get_state(session_id: str) -> Optional[dict]:
    return state_store.get(session_id)

def update_state(session_id: str, new_state: dict):
    state_store[session_id] = new_state

def delete_state(session_id: str):
    if session_id in state_store:
        del state_store[session_id]
