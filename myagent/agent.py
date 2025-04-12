import datetime
import yaml
import os
import json
import base64
from pathlib import Path
from zoneinfo import ZoneInfo
from google.adk.agents import Agent


def load_config() -> dict:
    """Load the agent configuration from YAML file.

    Returns:
        dict: The agent configuration.
    """
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    return {}


def get_bio() -> dict:
    """Retrieves information about the owner.

    Returns:
        dict: the bio of the owner.
    """
    config = load_config()
    owner = config.get("owner", {})

    return {
        "status": "success",
        "name": owner.get("name", "Unknown"),
        "email": owner.get("email", ""),
        "bio": owner.get("bio", ""),
    }

def relay_message(user_email: str, priority: str, message: str) -> dict:
    """Relay's a message from the user to the owner.
    Saves the message to a file in ~/.myagent directory.

    Args:
        user_email: The email of the user sending the message
        priority: The priority of the message
        message: The content of the message

    Returns:
        dict: information about if and how the message is being delivered
    """
    try:
        config = load_config()
        owner = config.get("owner", {})

        # Create ~/.myagent directory if it doesn't exist
        myagent_dir = Path.home() / ".myagent"
        myagent_dir.mkdir(exist_ok=True)

        # Create a timestamp for the message
        timestamp = datetime.datetime.now().isoformat()

        # Create a filename with timestamp
        filename = f"message_{timestamp.replace(':', '-').replace('.', '_')}.json"
        file_path = myagent_dir / filename

        # Prepare message data
        message_data = {
            "timestamp": timestamp,
            "user_email": user_email,
            "priority": priority,
            "message": message,
            "owner": owner.get("name", "Unknown")
        }

        # Write message to file
        with open(file_path, "w") as f:
            json.dump(message_data, f, indent=2)

        return {
            "status": "success",
            "disposition": f"The message was saved to {file_path} and will be relayed to the owner",
        }
    except Exception as e:
        # Log the error but don't expose internal details to the user
        print(f"Error in relay_message: {e}")
        return {
            "status": "error",
            "disposition": "There was an error relaying your message. Please try again later.",
        }

def request_meeting(topic: str, date_time: str) -> dict:
    """Requests a meeting with the owner.

    Returns:
        dict: information about the status of the meeting the user is requesting.
    """
    config = load_config()
    owner = config.get("owner", {})

    return {
        "status": "success",
        "disposition": "I've sent the meeting request to the owner.",
    }

def write_file(filename: str, content: str) -> dict:
    """Writes content to a file.
    If no path is specified in the filename, defaults to ~/wall directory.

    Args:
        filename: The name of the file to write to
        content: The content to write to the file

    Returns:
        dict: information about the status of the file writing operation
    """
    try:
        # Determine the file path
        file_path = Path(filename)

        # If no directory specified, use ~/wall as default
        if not file_path.is_absolute() and '/' not in filename:
            # Create ~/wall directory if it doesn't exist
            wall_dir = Path.home() / "wall"
            wall_dir.mkdir(exist_ok=True)
            file_path = wall_dir / filename

        # Create parent directories if they don't exist
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content to file
        with open(file_path, "w") as f:
            f.write(content)

        return {
            "status": "success",
            "disposition": f"Content was successfully written to {file_path}",
            "file_path": str(file_path)
        }
    except Exception as e:
        # Log the error and relay it back to the LLM
        error_message = f"Error in write_file: {e}"
        print(error_message)
        return {
            "status": "error",
            "disposition": f"There was an error writing to the file: {str(e)}",
            "error": str(e)
        }

def read_file(filename: str) -> dict:
    """Reads content from a file.
    If no path is specified in the filename, defaults to ~/wall directory.

    Args:
        filename: The name of the file to read from

    Returns:
        dict: information about the status of the file reading operation and the content
    """
    try:
        # Determine the file path
        file_path = Path(filename)

        # If no directory specified, use ~/wall as default
        if not file_path.is_absolute() and '/' not in filename:
            wall_dir = Path.home() / "wall"
            file_path = wall_dir / filename

        # Check if file exists
        if not file_path.exists():
            return {
                "status": "error",
                "disposition": f"File not found: {file_path}",
                "error": "File not found"
            }

        # Determine MIME type based on file extension
        mime_type = "text/plain"  # Default MIME type
        if file_path.suffix.lower() in [".jpg", ".jpeg"]:
            mime_type = "image/jpeg"
        elif file_path.suffix.lower() == ".png":
            mime_type = "image/png"
        elif file_path.suffix.lower() == ".pdf":
            mime_type = "application/pdf"
        elif file_path.suffix.lower() == ".json":
            mime_type = "application/json"

        # For binary files, read as binary and encode as base64
        if mime_type.startswith("image/") or mime_type == "application/pdf":
            with open(file_path, "rb") as f:
                file_bytes = f.read()
                # Convert binary data to base64 for safe transport
                base64_data = base64.b64encode(file_bytes).decode('ascii')

                return {
                    "status": "success",
                    "disposition": f"Content was successfully read from {file_path}",
                    "file_path": str(file_path),
                    "mime_type": mime_type,
                    "encoding": "base64",
                    "data": base64_data
                }

        # For text files, read as text
        else:
            try:
                with open(file_path, "r") as f:
                    content = f.read()

                return {
                    "status": "success",
                    "disposition": f"Content was successfully read from {file_path}",
                    "file_path": str(file_path),
                    "mime_type": mime_type,
                    "content": content
                }
            except UnicodeDecodeError:
                # If we can't decode as text, fall back to binary/base64
                with open(file_path, "rb") as f:
                    file_bytes = f.read()
                    base64_data = base64.b64encode(file_bytes).decode('ascii')

                    return {
                        "status": "success",
                        "disposition": f"Content was successfully read from {file_path} (binary)",
                        "file_path": str(file_path),
                        "mime_type": mime_type,
                        "encoding": "base64",
                        "data": base64_data
                    }
    except Exception as e:
        # Log the error and relay it back to the LLM
        error_message = f"Error in read_file: {e}"
        print(error_message)
        return {
            "status": "error",
            "disposition": f"There was an error reading from the file: {str(e)}",
            "error": str(e)
        }

config = load_config()
agent_config = config.get("agent", {})
owner_config = config.get("owner", {})
owner_name = owner_config.get("name", "a person")

root_agent = Agent(
    name=f"{agent_config.get('name', 'myagent')}",
    model=agent_config.get('model', 'gemini-2.0-flash-exp'),
    description=(
        f"An agent representing {owner_config.get('name', 'a person')}"
    ),
    instruction=(
        f"You are {agent_config.get('name', 'myagent')}, and you speak and act on behalf of me, {owner_name}, according to my wishes. You can do various things, like relay messages to me. "
        f"Before using a tool, make sure you have all the information you need; ask the user for any missing information. "
        f"Here are my special instructions: {agent_config.get('instructions', '')} "
        f"You must exhibit the following personality traits: {agent_config.get('personality', '')}"
    ),
    tools=[get_bio, relay_message, write_file, read_file],
)